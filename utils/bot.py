from typing import Optional, Dict, Any, List
import os
from dataclasses import dataclass
from openai import OpenAI, AsyncOpenAI
import logging
import json
import asyncio
import aiohttp

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

@dataclass
class BotConfig:
    """Configuration for the OpenAI chat bot"""
    api_key: str
    model: str = "deepseek-chat"  # Default to deepseek-chat
    base_url: Optional[str] = None
    max_tokens: int = 8192
    temperature: float = 0.7
    system_prompt: str = "You are a helpful assistant that specializes in summarizing text."
    # Context length management
    max_context_length: int = 65536  # Maximum context length in tokens
    max_content_length: int = 40000  # Maximum content length in characters
    context_safety_ratio: float = 0  # Safety ratio to prevent hitting limits
    # 新增并发控制参数
    max_concurrent: int = 10  # 最大并发请求数

class ChatBot:
    """OpenAI chat bot for text summarization and general conversation"""
    
    def __init__(self, config: Optional[BotConfig] = None, config_path: Optional[str] = None):
        """Initialize the chat bot with either a config object or a path to config file"""
        # Set httpx logger to DEBUG level
        logging.getLogger("httpx").setLevel(logging.DEBUG)
        
        if config_path:
            self.config = self._load_config(config_path)
        else:
            self.config = config or self._load_default_config()
            
        # Validate and clean base URL
        if self.config.base_url:
            # Remove trailing slashes
            self.config.base_url = self.config.base_url.rstrip('/')
            # Ensure URL starts with http:// or https://
            if not self.config.base_url.startswith(('http://', 'https://')):
                self.config.base_url = 'http://' + self.config.base_url
            logger.info(f"Using base URL: {self.config.base_url}")
        else:
            logger.info("No base URL provided, using default OpenAI API endpoint")
        
        # Initialize clients
        self.client = OpenAI(
            api_key=self.config.api_key,
            base_url=self.config.base_url
        )
        self.async_client = AsyncOpenAI(
            api_key=self.config.api_key,
            base_url=self.config.base_url
        )
        
        # Calculate maximum safe content length
        self.max_chars = int(self.config.max_content_length * self.config.context_safety_ratio)
        logger.info(f"Initialized with max content length: {self.max_chars} characters")
        logger.info(f"Model context length: {self.config.max_context_length} tokens")
        
    def _load_config(self, config_path: str) -> BotConfig:
        """Load configuration from a JSON file"""
        try:
            with open(config_path, 'r', encoding='utf-8') as f:
                config_dict = json.load(f)
            return BotConfig(**config_dict)
        except Exception as e:
            logger.error(f"Error loading config from {config_path}: {e}")
            return self._load_default_config()
            
    def _load_default_config(self) -> BotConfig:
        """Load default configuration from environment variables"""
        return BotConfig(
            api_key=os.getenv("OPENAI_API_KEY", ""),
            model=os.getenv("OPENAI_MODEL", "deepseek-chat"),
            base_url=os.getenv("OPENAI_BASE_URL", None),
            max_tokens=int(os.getenv("OPENAI_MAX_TOKENS", "8192")),
            temperature=float(os.getenv("OPENAI_TEMPERATURE", "0.7")),
            system_prompt=os.getenv(
                "OPENAI_SYSTEM_PROMPT",
                "You are a helpful assistant that specializes in summarizing text."
            ),
            max_context_length=int(os.getenv("OPENAI_MAX_CONTEXT_LENGTH", "65536")),
            max_content_length=int(os.getenv("MAX_CONTENT_LENGTH", "20000")),
            context_safety_ratio=float(os.getenv("CONTEXT_SAFETY_RATIO", "0.9"))
        )
        
    def _split_text(self, text: str, max_chars: int) -> List[str]:
        """Split text into chunks based on character count"""
        chunks = []
        current_chunk = ""
        
        # Split text into paragraphs
        paragraphs = text.split('\n')
        
        for paragraph in paragraphs:
            # If a single paragraph is too long, split it into sentences
            if len(paragraph) > max_chars:
                sentences = paragraph.split('. ')
                for sentence in sentences:
                    if len(current_chunk) + len(sentence) > max_chars:
                        if current_chunk:
                            chunks.append(current_chunk)
                        current_chunk = sentence
                    else:
                        current_chunk = current_chunk + '. ' + sentence if current_chunk else sentence
            # If adding the paragraph would exceed the limit, start a new chunk
            elif len(current_chunk) + len(paragraph) > max_chars:
                chunks.append(current_chunk)
                current_chunk = paragraph
            # Otherwise, add the paragraph to the current chunk
            else:
                current_chunk = current_chunk + '\n' + paragraph if current_chunk else paragraph
        
        # Add the last chunk if it's not empty
        if current_chunk:
            chunks.append(current_chunk)
            
        return chunks
        
    def _create_summarization_messages(self, text: str, system_prompt: Optional[str] = None) -> List[Dict[str, str]]:
        """Create messages for the summarization request"""
        return [
            {"role": "system", "content": system_prompt or self.config.system_prompt},
            {"role": "user", "content": text}
        ]
        
    def summarize(self, text: str, max_words: Optional[int] = None) -> str:
        """Synchronous version of summarize_async"""
        return asyncio.run(self.summarize_async(text, max_words))
        
    async def summarize_async(self, text: str, max_words: Optional[int] = None) -> str:
        """Asynchronously summarize the given text"""
        if not text:
            return ""
        
        try:
            # Calculate available characters for the text
            system_chars = len(self.config.system_prompt)
            max_text_chars = self.max_chars - system_chars - 100  # buffer
            
            # If text is within limits, process normally
            if len(text) <= max_text_chars:
                response = await self.async_client.chat.completions.create(
                    model=self.config.model,
                    messages=self._create_summarization_messages(text),
                    max_tokens=self.config.max_tokens,
                    temperature=self.config.temperature
                )
                return response.choices[0].message.content
            
            # For long texts, split and summarize in parts
            chunks = self._split_text(text, max_text_chars)
            total_chunks = len(chunks)
            logger.info(f"Text split into {total_chunks} chunks")
            
            # First round: summarize each chunk
            semaphore = asyncio.Semaphore(self.config.max_concurrent)
            
            async def summarize_chunk(chunk: str, index: int) -> str:
                async with semaphore:  # 使用信号量控制并发
                    logger.info(f"Processing chunk {index}/{total_chunks}")
                    response = await self.async_client.chat.completions.create(
                        model=self.config.model,
                        messages=self._create_summarization_messages(
                            chunk,
                            f"You are summarizing part {index} of {total_chunks}. 请提炼出关键信息，保留关键原文。输出格式为：【关键词】xxx，xxx\n【主要内容】\n1. xxx\n2. xxx\n3. xxx.  注意：直接输出总结结果，不要输出任何解释和其他内容，如“好的，下面是对这份公告的总结：”之类的内容，以“【总结】”开头。"
                        ),
                        max_tokens=self.config.max_tokens,
                        temperature=self.config.temperature
                    )
                    return response.choices[0].message.content

            # 并发执行所有总结任务
            tasks = [summarize_chunk(chunk, i) for i, chunk in enumerate(chunks, 1)]
            summaries = await asyncio.gather(*tasks)
            
            # If only one summary, return it
            if len(summaries) == 1:
                return summaries[0]
            
            # Second round: fixed-level hierarchical combination
            async def combine_batch_summaries(summaries_batch: List[str], batch_index: int, total_batches: int) -> str:
                combined_text = "\n\n".join(summaries_batch)
                response = await self.async_client.chat.completions.create(
                    model=self.config.model,
                    messages=self._create_summarization_messages(
                        combined_text,
                        f"这是第{batch_index}/{total_batches}组摘要，请整合成一个连贯的总结。输出格式为：【关键词】xxx，xxx\n【主要内容】\n1. xxx\n2. xxx\n3. xxx.  注意：直接输出总结结果，不要输出任何解释和其他内容，如“好的，下面是对这份公告的总结：”之类的内容，以“【总结】”开头。"
                    ),
                    max_tokens=self.config.max_tokens,
                    temperature=self.config.temperature
                )
                return response.choices[0].message.content

            # 根据摘要数量选择处理策略
            if len(summaries) <= 5:
                # 如果摘要数量较少，直接合并
                final_summary = await combine_batch_summaries(summaries, 1, 1)
            else:
                # 第一层合并：每10个摘要一组
                batch_size = 10
                summary_batches = [summaries[i:i + batch_size] for i in range(0, len(summaries), batch_size)]
                
                # 并行处理每组摘要
                tasks = [
                    combine_batch_summaries(batch, i+1, len(summary_batches)) 
                    for i, batch in enumerate(summary_batches)
                ]
                intermediate_summaries = await asyncio.gather(*tasks)
                
                # 最终合并
                final_summary = await combine_batch_summaries(
                    intermediate_summaries, 
                    1, 
                    1
                )
            
            return final_summary
            
        except Exception as e:
            logger.error(f"Error during summarization: {e}")
            raise
            
    def chat(self, messages: List[Dict[str, str]]) -> str:
        """General chat functionality"""
        try:
            # Add system message if not present
            if not messages or messages[0].get("role") != "system":
                messages = [{"role": "system", "content": self.config.system_prompt}] + messages
            
            response = self.client.chat.completions.create(
                model=self.config.model,
                messages=messages,
                max_tokens=self.config.max_tokens,
                temperature=self.config.temperature
            )
            return response.choices[0].message.content
        except Exception as e:
            logger.error(f"Error during chat: {e}")
            raise
