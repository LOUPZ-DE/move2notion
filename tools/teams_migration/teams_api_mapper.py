#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
Teams API Mapper - Microsoft Graph JSON → typisierte Dataclasses.

Reine Datenkonvertierung ohne Side-Effects (keine API-Calls, kein I/O).
Alle Funktionen sind isoliert testbar mit Sample-JSON.
"""
from dataclasses import dataclass, field
from typing import List, Optional, Dict, Any
import re


@dataclass
class Channel:
    """Microsoft Teams Channel."""
    id: str
    display_name: str
    channel_type: str  # "standard" | "private" | "shared"
    created_dt: Optional[str] = None
    description: Optional[str] = None
    web_url: Optional[str] = None


@dataclass
class Reaction:
    """Reaction auf eine Teams-Message."""
    reaction_type: str  # "like", "heart", "laugh", "surprised", "sad", "angry", custom-emoji
    user_display_name: str
    created_dt: Optional[str] = None


@dataclass
class Mention:
    """@-Mention in einer Teams-Message."""
    mention_id: int  # numerische ID innerhalb der Message
    display_name: str
    email: Optional[str] = None
    mention_type: str = "user"  # "user" | "team" | "channel" | "tag"


@dataclass
class Attachment:
    """Anhang an einer Teams-Message (Datei oder Karte)."""
    attachment_type: str  # "reference" (SharePoint-Datei), "messageReference", "tabReference", etc.
    name: Optional[str] = None
    content_url: Optional[str] = None  # Bei reference: SharePoint-Link
    content_type: Optional[str] = None
    thumbnail_url: Optional[str] = None
    # Microsoft schickt fuer Inline-Bilder oft Attachments ohne contentUrl, deren
    # `id` der hostedContent-ID entspricht. Wird zum direkten Bild-Download genutzt.
    id: Optional[str] = None


@dataclass
class HostedContent:
    """Inline-hostedContent (z. B. eingebettetes Bild) referenziert in Message-Body."""
    hosted_content_id: str
    content_type: Optional[str] = None  # z. B. "image/png"


@dataclass
class Message:
    """Top-Level Message oder Reply in einem Teams-Channel."""
    id: str
    created_dt: Optional[str] = None
    last_modified_dt: Optional[str] = None
    from_display_name: str = "Unbekannt"
    from_email: Optional[str] = None
    from_user_id: Optional[str] = None
    body_html: str = ""
    body_content_type: str = "html"  # "html" | "text"
    subject: Optional[str] = None
    importance: str = "normal"  # "normal" | "high" | "urgent"
    message_type: str = "message"  # "message" | "chatEvent" | "typing" | ...
    is_deleted: bool = False
    attachments: List[Attachment] = field(default_factory=list)
    mentions: List[Mention] = field(default_factory=list)
    reactions: List[Reaction] = field(default_factory=list)
    hosted_contents: List[HostedContent] = field(default_factory=list)
    replies: List["Message"] = field(default_factory=list)


def _safe_str(value: Any, default: str = "") -> str:
    """Hilfsfunktion: tolerantes String-Casting fuer optionale Felder."""
    if value is None:
        return default
    return str(value)


def map_channel_raw(raw: Dict[str, Any]) -> Channel:
    """Microsoft Graph Channel-JSON in `Channel` Dataclass abbilden."""
    return Channel(
        id=raw.get("id", ""),
        display_name=raw.get("displayName", "(unbenannt)"),
        channel_type=raw.get("membershipType", "standard"),
        created_dt=raw.get("createdDateTime"),
        description=raw.get("description"),
        web_url=raw.get("webUrl"),
    )


def _map_from(raw_from: Optional[Dict[str, Any]]) -> Dict[str, Optional[str]]:
    """Absender-Feld extrahieren (User, Application, Device).

    Teams liefert `from` in unterschiedlichen Formen:
      {"user": {"displayName": "...", "id": "...", "userIdentityType": "..."}}
      {"application": {"displayName": "...", "id": "..."}}
      None (System-Messages)
    """
    if not raw_from:
        return {"display_name": "System", "email": None, "user_id": None}

    user = raw_from.get("user") or {}
    if user:
        return {
            "display_name": user.get("displayName") or "Unbekannt",
            "email": user.get("email") or user.get("userPrincipalName"),
            "user_id": user.get("id"),
        }

    app = raw_from.get("application") or {}
    if app:
        return {
            "display_name": app.get("displayName") or "App",
            "email": None,
            "user_id": app.get("id"),
        }

    device = raw_from.get("device") or {}
    if device:
        return {
            "display_name": "Geraet",
            "email": None,
            "user_id": None,
        }

    return {"display_name": "Unbekannt", "email": None, "user_id": None}


def _map_attachments(raw_attachments: List[Dict[str, Any]]) -> List[Attachment]:
    items = []
    for att in raw_attachments or []:
        items.append(Attachment(
            attachment_type=att.get("contentType") or att.get("@odata.type") or "reference",
            name=att.get("name"),
            content_url=att.get("contentUrl"),
            content_type=att.get("contentType"),
            thumbnail_url=att.get("thumbnailUrl"),
            id=att.get("id"),
        ))
    return items


def _map_mentions(raw_mentions: List[Dict[str, Any]]) -> List[Mention]:
    items = []
    for m in raw_mentions or []:
        mentioned = m.get("mentioned") or {}
        user = mentioned.get("user") or {}
        conv_id_type = mentioned.get("conversation", {}).get("conversationIdentityType")
        mention_type = "user" if user else (conv_id_type or "tag")
        items.append(Mention(
            mention_id=int(m.get("id", 0) or 0),
            display_name=m.get("mentionText")
                         or user.get("displayName")
                         or "(Erwaehnung)",
            email=user.get("email") or user.get("userPrincipalName"),
            mention_type=mention_type,
        ))
    return items


def _map_reactions(raw_reactions: List[Dict[str, Any]]) -> List[Reaction]:
    items = []
    for r in raw_reactions or []:
        user = (r.get("user") or {}).get("user") or {}
        items.append(Reaction(
            reaction_type=r.get("reactionType") or "like",
            user_display_name=user.get("displayName") or "Unbekannt",
            created_dt=r.get("createdDateTime"),
        ))
    return items


_HOSTED_CONTENT_RE = re.compile(
    r"hostedContents/([^/'\"\s\)]+)/\$value", re.IGNORECASE
)


def _extract_hosted_contents(body_content: str) -> List[HostedContent]:
    """hostedContent-IDs aus Message-Body extrahieren.

    Teams referenziert Inline-Bilder via
    `<img src="https://graph.microsoft.com/.../hostedContents/{id}/$value">`.
    """
    if not body_content:
        return []
    items = []
    seen = set()
    for match in _HOSTED_CONTENT_RE.finditer(body_content):
        hosted_id = match.group(1)
        if hosted_id in seen:
            continue
        seen.add(hosted_id)
        items.append(HostedContent(hosted_content_id=hosted_id))
    return items


def map_message_raw(raw: Dict[str, Any]) -> Message:
    """Microsoft Graph Message-JSON in `Message` Dataclass abbilden.

    Replies werden rekursiv ueber das `replies`-Feld (von `$expand=replies`)
    abgebildet, falls vorhanden.
    """
    body = raw.get("body") or {}
    body_content = body.get("content") or ""
    body_type = body.get("contentType") or "html"

    sender = _map_from(raw.get("from"))

    msg = Message(
        id=raw.get("id", ""),
        created_dt=raw.get("createdDateTime"),
        last_modified_dt=raw.get("lastModifiedDateTime"),
        from_display_name=sender["display_name"],
        from_email=sender["email"],
        from_user_id=sender["user_id"],
        body_html=body_content,
        body_content_type=body_type,
        subject=raw.get("subject"),
        importance=raw.get("importance") or "normal",
        message_type=raw.get("messageType") or "message",
        is_deleted=bool(raw.get("deletedDateTime")),
        attachments=_map_attachments(raw.get("attachments") or []),
        mentions=_map_mentions(raw.get("mentions") or []),
        reactions=_map_reactions(raw.get("reactions") or []),
        hosted_contents=_extract_hosted_contents(body_content),
    )

    # Replies ($expand=replies). Microsoft sortiert absteigend (neueste zuerst).
    raw_replies = raw.get("replies") or []
    msg.replies = [map_message_raw(r) for r in raw_replies]
    # Neueste zuletzt → chronologisch sortieren
    msg.replies.sort(key=lambda m: m.created_dt or "")

    return msg


def sort_messages_chronologically(messages: List[Message]) -> List[Message]:
    """Sortiert eine Liste von Top-Level-Messages chronologisch (oldest first)."""
    return sorted(messages, key=lambda m: m.created_dt or "")
