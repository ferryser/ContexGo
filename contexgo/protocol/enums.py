# -*- coding: utf-8 -*-

from enum import Enum

class ContextSource(str, Enum):
    """Context source enumeration"""
    INPUT_METRIC = "input_metric"
    WINDOW_FOCUS = "window_focus"
    DESKTOP_SNAPSHOT = "desktop_snapshot"
    CLIPBOARD_UPDATE = "clipboard_update"
    SYSTEM_LIFECYCLE = "system_lifecycle"
    FILE_MUTATION = "file_mutation"
    MEDIA_STATUS = "media_status"

class EventType(str, Enum):
    """Event type enumeration"""
    INPUT_METRIC = "input_metric"
    WINDOW_FOCUS = "window_focus"
    DESKTOP_SNAPSHOT = "desktop_snapshot"
    CLIPBOARD_UPDATE = "clipboard_update"
    SYSTEM_LIFECYCLE = "system_lifecycle"
    FILE_MUTATION = "file_mutation"
    MEDIA_STATUS = "media_status"

class FileType(str, Enum):
    """File type enumeration"""
    # 文档类型
    PDF = "pdf"
    DOCX = "docx"
    DOC = "doc"
    PPTX = "pptx"
    PPT = "ppt"
    # 表格类型
    FAQ_XLSX = "faq.xlsx"
    XLSX = "xlsx"
    XLS = "xls"
    CSV = "csv"
    JSONL = "jsonl"
    PARQUET = "parquet"
    # 图片类型
    PNG = "png"
    JPG = "jpg"
    JPEG = "jpeg"
    GIF = "gif"
    BMP = "bmp"
    WEBP = "webp"
    # 文本类型
    MD = "md"
    TXT = "txt"

STRUCTURED_FILE_TYPES = {
    FileType.XLSX,
    FileType.XLS,
    FileType.CSV,
    FileType.JSONL,
    FileType.PARQUET,
    FileType.FAQ_XLSX,
}

class ContentFormat(str, Enum):
    """Content format enumeration"""
    TEXT = "text"
    IMAGE = "image"
    FILE = "file"

class MergeType(str, Enum):
    """Merge type enumeration"""
    ASSOCIATIVE = "associative"
    SIMILARITY = "similarity"

class ContextType(str, Enum):
    """Context type enumeration"""
    ENTITY_CONTEXT = "entity_context"
    ACTIVITY_CONTEXT = "activity_context"
    INTENT_CONTEXT = "intent_context"
    SEMANTIC_CONTEXT = "semantic_context"
    PROCEDURAL_CONTEXT = "procedural_context"
    STATE_CONTEXT = "state_context"
    KNOWLEDGE_CONTEXT = "knowledge_context"
    WINDOW_FOCUS = "window_focus"

class VaultType(str, Enum):
    """Document type enumeration"""
    DAILY_REPORT = "DailyReport"
    WEEKLY_REPORT = "WeeklyReport"
    NOTE = "Note"

def get_context_type_options():
    """Get all available context type options"""
    return [ct.value for ct in ContextType]

def validate_context_type(context_type: str) -> bool:
    """Validate if the context type is valid"""
    return context_type in get_context_type_options()

def get_context_type_for_analysis(context_type_str: str) -> "ContextType":
    """Get context type for analysis with fault tolerance"""
    context_type_str = context_type_str.lower().strip()
    if validate_context_type(context_type_str):
        return ContextType(context_type_str)
    raise ValueError(f"Invalid context type: {context_type_str}")

class CompletionType(Enum):
    """Completion type enumeration"""
    SEMANTIC_CONTINUATION = "semantic_continuation"
    TEMPLATE_COMPLETION = "template_completion"
    REFERENCE_SUGGESTION = "reference_suggestion"
    CONTEXT_AWARE = "context_aware"
