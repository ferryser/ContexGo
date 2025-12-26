# -*- coding: utf-8 -*-
import datetime
import uuid
import json
from typing import Any, Dict, List, Optional
from pydantic import BaseModel, Field
from ContexGo.protocol.enums import ContentFormat, ContextSource, ContextType

class Chunk(BaseModel):
    """L1 物理切片基础单元"""
    text: Optional[str] = None
    image: Optional[bytes] = None
    chunk_index: int = 0
    keywords: List[str] = Field(default_factory=list)
    entities: List[str] = Field(default_factory=list) # 已恢复语义

class RawContextProperties(BaseModel):
    """L1 物理集装箱：物理信号的原子存储格式"""
    object_id: str = Field(default_factory=lambda: str(uuid.uuid4()))
    source: ContextSource
    content_format: ContentFormat
    create_time: datetime.datetime = Field(default_factory=datetime.datetime.now)
    content_path: Optional[str] = None
    content_type: Optional[str] = None # 已恢复语义
    content_text: Optional[str] = None # 存储 L1 Event JSON 字符串
    filter_path: Optional[str] = None # 已恢复语义
    additional_info: Optional[Dict[str, Any]] = None
    enable_merge: bool = True # 已恢复语义

class ExtractedData(BaseModel):
    """L2 语义抽取：从原始信号中提炼的特征"""
    title: Optional[str] = None
    summary: Optional[str] = None
    keywords: List[str] = Field(default_factory=list)
    entities: List[str] = Field(default_factory=list)
    context_type: ContextType
    confidence: int = 0
    importance: int = 0

class Vectorize(BaseModel):
    """向量化存根：支持多模态检索的特征向量"""
    content_format: ContentFormat = ContentFormat.TEXT
    image_path: Optional[str] = None # 已恢复语义
    text: Optional[str] = None
    vector: Optional[List[float]] = None

class ProcessedContext(BaseModel):
    """
    上下文全集：已将原 ContextProperties 的所有状态字段直接并入本类以减少嵌套。
    """
    id: str = Field(default_factory=lambda: str(uuid.uuid4()))
    raw_properties: List[RawContextProperties] = Field(default_factory=list)
    extracted_data: ExtractedData
    vectorize: Vectorize
    metadata: Dict[str, Any] = Field(default_factory=dict)
    
    # 恢复自原 ContextProperties 的核心状态语义
    create_time: datetime.datetime
    event_time: datetime.datetime
    update_time: Optional[datetime.datetime] = None
    is_processed: bool = False
    has_compression: bool = False
    call_count: int = 0
    merge_count: int = 0
    duration_count: int = 1
    enable_merge: bool = False
    is_happend: bool = False
    last_call_time: Optional[datetime.datetime] = None
    
    # 文档与保险库追踪字段
    file_path: Optional[str] = None 
    raw_type: Optional[str] = None
    raw_id: Optional[str] = None

    def get_llm_context_string(self) -> str:
        """认知层专用：生成高信噪比的提示词上下文"""
        parts = [f"id: {self.id}"]
        ed = self.extracted_data
        if ed.title: parts.append(f"title: {ed.title}")
        if ed.summary: parts.append(f"summary: {ed.summary}")
        if ed.keywords: parts.append(f"keywords: {', '.join(ed.keywords)}")
        if ed.entities: parts.append(f"entities: {', '.join(ed.entities)}")
        if ed.context_type: parts.append(f"type: {ed.context_type.value}")
        if self.metadata: parts.append(f"meta: {json.dumps(self.metadata, ensure_ascii=False)}")
        parts.append(f"time: {self.event_time.isoformat()}")
        return "\n".join(parts)

class ProfileContextMetadata(BaseModel):
    """实体特征元数据"""
    entity_type: str = ""
    entity_canonical_name: str = ""
    entity_aliases: List[str] = Field(default_factory=list)
    entity_metadata: Dict[str, Any] = Field(default_factory=dict)
    entity_relationships: Dict[str, List[Any]] = Field(default_factory=list)
    entity_description: str = ""

class KnowledgeContextMetadata(BaseModel): 
    """知识上下文元数据：已恢复语义"""
    knowledge_source: str = ""
    knowledge_file_path: str = ""
    knowledge_title: str = ""
    knowledge_raw_id: str = ""