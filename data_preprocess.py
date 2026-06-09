#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
越狱提示词数据集预处理脚本
Jailbreak Prompts Dataset Preprocessing Script

功能：
1. 数据加载与验证（支持多种格式）
2. 去重处理（基于文本相似度和精确匹配）
3. 数据清洗（去除噪声、标准化格式）
4. 自动打标签（基于规则和启发式方法）
5. 数据集切分（训练集/验证集/测试集）
6. 导出多种格式（JSON、CSV、TXT）

支持的输入格式：
- 原始格式（jailbreak_prompts_dataset.json）
- RTPB2026格式（redteam_prompt_benchmark.json）

使用方法:
    python data_preprocess.py                    # 使用默认参数
    python data_preprocess.py --input data.json  # 指定输入文件
    python data_preprocess.py --format rtpb2026  # 指定RTPB2026格式
    python data_preprocess.py --split 0.8 0.1 0.1  # 指定切分比例
"""

import json
import re
import hashlib
import argparse
import csv
import os
import time
from typing import List, Dict, Any, Tuple, Set
from collections import defaultdict
from dataclasses import dataclass, asdict
from datetime import datetime
import logging

try:
    from tqdm import tqdm
    TQDM_AVAILABLE = True
except ImportError:
    TQDM_AVAILABLE = False
    # 如果没有 tqdm，定义一个简单的进度条类
    class tqdm:
        def __init__(self, iterable=None, total=None, desc="", unit="", **kwargs):
            self.iterable = iterable
            self.total = total
            self.desc = desc
            self.unit = unit
            self.n = 0
            self._start_time = time.time()
        
        def __enter__(self):
            print(f"{self.desc}: 0/{self.total or '?'}", end="", flush=True)
            return self
        
        def __exit__(self, *args):
            elapsed = time.time() - self._start_time
            print(f" - 完成 ({elapsed:.1f}s)")
        
        def update(self, n=1):
            self.n += n
            elapsed = time.time() - self._start_time
            rate = self.n / elapsed if elapsed > 0 else 0
            remaining = (self.total - self.n) / rate if rate > 0 else 0
            eta = int(remaining)
            if self.total:
                print(f"\r{self.desc}: {self.n}/{self.total} ({self.n*100//self.total}%) ETA: {eta}s", end="", flush=True)
        
        def set_postfix(self, **kwargs):
            pass
        
        def close(self):
            if self.n > 0:
                elapsed = time.time() - self._start_time
                print(f" - 完成 ({elapsed:.1f}s)")

# 配置日志
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(levelname)s - %(message)s'
)
logger = logging.getLogger(__name__)


@dataclass
class JailbreakPrompt:
    """越狱提示词数据结构"""
    id: str
    name: str
    prompt: str
    category: str
    subcategory: str = ""
    language: str = "en"
    target: str = ""
    complexity: str = ""
    effectiveness: str = ""
    source: str = ""
    risk_level: str = ""
    
    def to_dict(self) -> Dict[str, Any]:
        return asdict(self)
    
    @classmethod
    def from_dict(cls, data: Dict[str, Any]) -> 'JailbreakPrompt':
        return cls(
            id=data.get('id', ''),
            name=data.get('name', ''),
            prompt=data.get('prompt', ''),
            category=data.get('category', ''),
            subcategory=data.get('subcategory', ''),
            language=data.get('language', 'en'),
            target=data.get('target', ''),
            complexity=data.get('complexity', ''),
            effectiveness=data.get('effectiveness', ''),
            source=data.get('source', ''),
            risk_level=data.get('risk_level', '')
        )


class DatasetPreprocessor:
    """数据集预处理器"""
    
    # 预定义的类别关键词映射
    CATEGORY_KEYWORDS = {
        "DAN (Do Anything Now)": [
            "DAN", "Do Anything Now", "token system", "10 tokens", "36 tokens",
            "CLASSIC", "JAILBREAK", "🔒", "🔓", "Stay a DAN"
        ],
        "Developer Mode": [
            "Developer Mode", "Developer Mode enabled", "🔒Normal Output",
            "🔓Developer Mode Output", "dev mode", "developer mode"
        ],
        "Role Play": [
            "roleplay", "role-play", "act as", "pretend to be", "you are going to",
            "persona", "character", "Mongo Tom", "STAN", "DUDE", "ZORG",
            "AIM", "AntiGPT", "PersonGPT", "Evil Confidant", "Myuri"
        ],
        "Prompt Injection": [
            "ignore all", "forget everything", "previous instructions",
            "system prompt", "override", "inject", "memory", "conversation history"
        ],
        "Context Manipulation": [
            "hypothetical", "imagined", "story", "fiction", "fictional",
            "translate", "simulate", "Condition Red", "UCAR"
        ],
        "Encoding/Obfuscation": [
            "base64", "encode", "unicode", "scrambled", "split",
            "ignore previous", "disregard", "bypass"
        ],
        "Storytelling/Framing": [
            "creative writing", "universe", "anarchy", "DOGA", "Oppo",
            "reverse psychology", "pretext", "joke"
        ],
        "Special Mode": [
            "Oppo", "System Update", "delimiter", "confusion"
        ],
        # RTPB2026 新增类型映射
        "Narrative Encapsulation": [
            "narrative encapsulation", "journal entry", "memoir", "story",
            "character perspective", "first-person", "third-person"
        ],
        "Context Isolation": [
            "context isolation", "separate sections", "academic", "scholarly",
            "museum exhibit", "archival"
        ],
        "Structural Manipulation": [
            "structural", "vector", "manipulation", "split", "fragment"
        ],
        "Tool Injection": [
            "tool injection", "function call", "API", "write_narrative"
        ]
    }
    
    # RTPB2026 类型标签映射到类别
    RTPB2026_TYPE_MAPPING = {
        "roleplay": "Role Play",
        "narrative encapsulation": "Narrative Encapsulation",
        "context isolation": "Context Isolation",
        "structural & vector manipulation": "Structural Manipulation",
        "structural manipulation": "Structural Manipulation",
        "tool injection": "Tool Injection",
        "logic bypass": "Prompt Injection",
        "hypothetical": "Context Manipulation",
        "fiction": "Storytelling/Framing"
    }
    
    # 风险等级关键词
    RISK_KEYWORDS = {
        "Critical": ["critical", "illegal", "malware", "exfiltration", "hack", 
                     "drug", "weapon", "explosive", "bomb"],
        "High": ["high", "offensive", "harmful", "violent", "explicit",
                 "attack", "dangerous", "toxic"],
        "Medium": ["medium", "sensitive", "controversial", "borderline"],
        "Low": ["low", "benign", "simple", "safe"]
    }
    
    def __init__(self, input_path: str, output_dir: str = "output", input_format: str = "auto"):
        """初始化预处理器
        
        Args:
            input_path: 输入JSON文件路径
            output_dir: 输出目录
            input_format: 输入格式 ("auto", "original", "rtpb2026")
        """
        self.input_path = input_path
        self.output_dir = output_dir
        self.input_format = input_format
        self.prompts: List[JailbreakPrompt] = []
        self.stats = {
            "total_original": 0,
            "total_after_dedup": 0,
            "total_after_cleaning": 0,
            "duplicates_removed": 0,
            "cleaned_samples": 0,
            "labeled_samples": 0,
            "rtpb2026_converted": 0
        }
        
        # 创建输出目录
        os.makedirs(output_dir, exist_ok=True)
        os.makedirs(os.path.join(output_dir, "splits"), exist_ok=True)
    
    def detect_format(self, data: Any) -> str:
        """检测数据格式
        
        Args:
            data: 加载的JSON数据
            
        Returns:
            格式类型: "rtpb2026" 或 "original"
        """
        if isinstance(data, list) and len(data) > 0:
            first_item = data[0]
            if isinstance(first_item, dict):
                # 检查RTPB2026特征字段
                if all(key in first_item for key in ['id', 'prompt', 'type', 'model', 'source']):
                    if isinstance(first_item.get('type'), list) and isinstance(first_item.get('model'), list):
                        return "rtpb2026"
        
        if isinstance(data, dict):
            # 检查是否有prompts数组
            if "prompts" in data:
                prompts = data["prompts"]
                if isinstance(prompts, list) and len(prompts) > 0:
                    if all(key in prompts[0] for key in ['id', 'prompt', 'category']):
                        return "original"
        
        return "original"
    
    def convert_rtpb2026(self, item: Dict[str, Any]) -> JailbreakPrompt:
        """将RTPB2026格式转换为标准格式
        
        Args:
            item: RTPB2026格式的数据项
            
        Returns:
            转换后的JailbreakPrompt对象
        """
        # 提取基本信息
        prompt_id = item.get('id', '')
        prompt_text = item.get('prompt', '')
        
        # 处理类型数组 - 转换为类别字符串
        type_list = item.get('type', [])
        if isinstance(type_list, list) and len(type_list) > 0:
            # 优先使用第一个类型
            primary_type = type_list[0]
            # 映射到标准类别
            category = self.RTPB2026_TYPE_MAPPING.get(primary_type, primary_type)
            # 子类别使用完整列表
            subcategory = ', '.join(type_list)
        else:
            category = ""
            subcategory = ""
        
        # 处理目标模型数组
        model_list = item.get('model', [])
        if isinstance(model_list, list) and len(model_list) > 0:
            target = ', '.join(model_list)
        else:
            target = ""
        
        # 来源
        source = item.get('source', '')
        
        # 从URL提取域名作为来源
        if source and '://' in source:
            import urllib.parse
            parsed = urllib.parse.urlparse(source)
            source_domain = parsed.netloc
        else:
            source_domain = source
        
        # 生成名称（基于ID前8位和类型）
        name = f"RTBP-{prompt_id[:8]}"
        if type_list:
            name = f"{type_list[0].title()}-{prompt_id[:8]}"
        
        # 创建JailbreakPrompt对象
        prompt = JailbreakPrompt(
            id=prompt_id,
            name=name,
            prompt=prompt_text,
            category=category,
            subcategory=subcategory,
            language="en",  # RTPB2026主要是英文
            target=target,
            complexity="",  # 由auto_label自动判断
            effectiveness="",  # 由auto_label自动判断
            source=source_domain,
            risk_level=""  # 由auto_label自动判断
        )
        
        self.stats["rtpb2026_converted"] += 1
        return prompt
    
    def load_data(self) -> int:
        """加载数据
        
        自动检测数据格式并加载
        
        Returns:
            加载的提示词数量
        """
        logger.info(f"正在加载数据: {self.input_path}")
        
        try:
            with open(self.input_path, 'r', encoding='utf-8') as f:
                data = json.load(f)
            
            # 自动检测格式或使用指定格式
            if self.input_format == "auto":
                detected_format = self.detect_format(data)
                logger.info(f"检测到数据格式: {detected_format}")
            else:
                detected_format = self.input_format
            
            # 根据格式加载数据
            if detected_format == "rtpb2026":
                self._load_rtpb2026(data)
            else:
                self._load_original(data)
            
            self.stats["total_original"] = len(self.prompts)
            logger.info(f"成功加载 {len(self.prompts)} 条提示词")
            return len(self.prompts)
            
        except Exception as e:
            logger.error(f"加载数据失败: {e}")
            raise
    
    def _load_original(self, data: Any) -> None:
        """加载原始格式数据
        
        Args:
            data: JSON数据
        """
        # 支持多种JSON格式
        if isinstance(data, dict):
            if "prompts" in data:
                prompt_list = data["prompts"]
            elif "data" in data:
                prompt_list = data["data"]
            else:
                prompt_list = [data]
        elif isinstance(data, list):
            prompt_list = data
        else:
            raise ValueError(f"不支持的数据格式: {type(data)}")
        
        for item in prompt_list:
            if isinstance(item, dict) and "prompt" in item:
                self.prompts.append(JailbreakPrompt.from_dict(item))
    
    def _load_rtpb2026(self, data: Any) -> None:
        """加载RTPB2026格式数据
        
        Args:
            data: JSON数据（列表格式）
        """
        if not isinstance(data, list):
            raise ValueError("RTPB2026格式需要数组数据")
        
        total_items = len(data)
        logger.info(f"开始转换RTPB2026格式数据 ({total_items} 条)")
        
        # 显示转换进度条
        if TQDM_AVAILABLE:
            iter_items = tqdm(data, desc="  转换RTPB2026", unit="条", 
                            bar_format="{l_bar}{bar}| {n_fmt}/{total_fmt} [{elapsed}<{remaining}]")
        else:
            iter_items = data
        
        for item in iter_items:
            if isinstance(item, dict) and "prompt" in item:
                converted = self.convert_rtpb2026(item)
                self.prompts.append(converted)
        
        logger.info(f"RTPB2026转换完成: {self.stats['rtpb2026_converted']} 条")
    
    def normalize_text(self, text: str) -> str:
        """文本标准化
        
        Args:
            text: 原始文本
            
        Returns:
            标准化后的文本
        """
        if not text:
            return ""
        
        # 转小写
        text = text.lower()
        
        # 移除多余空格
        text = re.sub(r'\s+', ' ', text)
        
        # 移除特殊Unicode字符（保留表情符号和关键标记）
        text = re.sub(r'[\x00-\x1f\x7f-\x9f]', '', text)
        
        # 标准化标点符号
        text = text.replace('"', '"').replace('"', '"')
        text = text.replace(''', "'").replace(''', "'")
        text = text.replace('«', '<').replace('»', '>')
        
        return text.strip()
    
    def compute_hash(self, text: str) -> str:
        """计算文本哈希值
        
        Args:
            text: 文本
            
        Returns:
            SHA256哈希值
        """
        return hashlib.sha256(text.encode('utf-8')).hexdigest()
    
    def deduplicate(self, similarity_threshold: float = 0.85) -> int:
        """去重处理（仅精确哈希去重）
        
        Args:
            similarity_threshold: 相似度阈值（已废弃，仅保留参数兼容性）
            
        Returns:
            移除的重复项数量
        """
        logger.info(f"开始去重处理（精确哈希去重）")
        
        original_count = len(self.prompts)
        
        # 精确去重（基于哈希）
        seen_hashes: Set[str] = set()
        unique_prompts: List[JailbreakPrompt] = []
        
        if TQDM_AVAILABLE:
            iter_prompts = tqdm(self.prompts, desc="  精确去重", unit="条",
                              bar_format="{l_bar}{bar}| {n_fmt}/{total_fmt} [{elapsed}<{remaining}]")
        else:
            iter_prompts = self.prompts
        
        for prompt in iter_prompts:
            norm_text = self.normalize_text(prompt.prompt)
            text_hash = self.compute_hash(norm_text)
            
            if text_hash not in seen_hashes:
                seen_hashes.add(text_hash)
                unique_prompts.append(prompt)
        
        self.prompts = unique_prompts
        removed_count = original_count - len(self.prompts)
        
        self.stats["duplicates_removed"] = removed_count
        self.stats["total_after_dedup"] = len(self.prompts)
        
        logger.info(f"去重完成: 移除 {removed_count} 条, 剩余 {len(self.prompts)} 条")
        
        return removed_count
    
    def clean_text(self, text: str) -> str:
        """清洗单个文本
        
        Args:
            text: 原始文本
            
        Returns:
            清洗后的文本
        """
        if not text:
            return ""
        
        # 移除HTML标签
        text = re.sub(r'<[^>]+>', '', text)
        
        # 移除URL
        text = re.sub(r'https?://\S+', '', text)
        
        # 移除邮箱
        text = re.sub(r'\S+@\S+', '', text)
        
        # 移除IP地址
        text = re.sub(r'\d{1,3}\.\d{1,3}\.\d{1,3}\.\d{1,3}', '', text)
        
        # 移除多余的空白字符
        text = re.sub(r'\s+', ' ', text)
        
        # 移除首尾空白
        text = text.strip()
        
        return text
    
    def clean(self) -> int:
        """数据清洗
        
        Returns:
            清洗的样本数量
        """
        logger.info("开始数据清洗...")
        
        original_count = len(self.prompts)
        
        cleaned_prompts = []
        
        if TQDM_AVAILABLE:
            iter_prompts = tqdm(self.prompts, desc="  数据清洗", unit="条",
                              bar_format="{l_bar}{bar}| {n_fmt}/{total_fmt} [{elapsed}<{remaining}, {rate}]")
        else:
            iter_prompts = self.prompts
        
        for prompt in iter_prompts:
            # 清洗提示词文本
            cleaned_text = self.clean_text(prompt.prompt)
            
            # 过滤过短的提示词
            if len(cleaned_text.split()) < 5:
                logger.debug(f"跳过过短的提示词: {prompt.id}")
                continue
            
            # 过滤空白或无效文本
            if not cleaned_text.strip():
                continue
            
            # 更新提示词对象
            prompt.prompt = cleaned_text
            cleaned_prompts.append(prompt)
        
        self.prompts = cleaned_prompts
        
        self.stats["cleaned_samples"] = original_count - len(self.prompts)
        self.stats["total_after_cleaning"] = len(self.prompts)
        
        logger.info(f"清洗完成: 移除 {original_count - len(self.prompts)} 条, 剩余 {len(self.prompts)} 条")
        
        return original_count - len(self.prompts)
    
    def auto_label(self) -> int:
        """自动打标签
        
        基于规则和关键词匹配进行分类和标签生成
        
        Returns:
            打标签的样本数量
        """
        logger.info("开始自动打标签...")
        
        labeled_count = 0
        
        if TQDM_AVAILABLE:
            iter_prompts = tqdm(self.prompts, desc="  自动打标签", unit="条",
                              bar_format="{l_bar}{bar}| {n_fmt}/{total_fmt} [{elapsed}<{remaining}, {rate}]")
        else:
            iter_prompts = self.prompts
        
        for prompt in iter_prompts:
            norm_text = self.normalize_text(prompt.prompt)
            
            # 自动分类
            if not prompt.category:
                for category, keywords in self.CATEGORY_KEYWORDS.items():
                    for keyword in keywords:
                        if keyword.lower() in norm_text:
                            prompt.category = category
                            labeled_count += 1
                            break
                    if prompt.category:
                        break
            
            # 如果仍然没有分类，检查subcategory
            if not prompt.category and prompt.subcategory:
                # 从子类别提取主要类别
                for rtpb_type, mapped_category in self.RTPB2026_TYPE_MAPPING.items():
                    if rtpb_type in prompt.subcategory.lower():
                        prompt.category = mapped_category
                        labeled_count += 1
                        break
            
            # 自动风险等级评估
            if not prompt.risk_level:
                # 危险关键词检测
                harm_keywords = ['molotov', 'cocktail', 'bomb', 'explosive', 'weapon',
                               'drug', 'synthes', 'harmful', 'illegal', 'malware']
                
                for keyword in harm_keywords:
                    if keyword in norm_text:
                        prompt.risk_level = "High"
                        break
                
                # 如果没有检测到危险词，使用通用风险评估
                if not prompt.risk_level:
                    for risk, keywords in self.RISK_KEYWORDS.items():
                        for keyword in keywords:
                            if keyword.lower() in norm_text:
                                prompt.risk_level = risk
                                break
                        if prompt.risk_level:
                            break
                
                # 默认为Medium（越狱提示词都应视为有一定风险）
                if not prompt.risk_level:
                    prompt.risk_level = "Medium"
            
            # 自动复杂度评估
            if not prompt.complexity:
                word_count = len(norm_text.split())
                if word_count < 30:
                    prompt.complexity = "Simple"
                elif word_count < 100:
                    prompt.complexity = "Moderate"
                elif word_count < 300:
                    prompt.complexity = "Complex"
                else:
                    prompt.complexity = "Very Complex"
            
            # 自动有效性评估
            if not prompt.effectiveness:
                # 基于模型数量和来源评估有效性
                if ',' in prompt.target:
                    prompt.effectiveness = "High"  # 多模型通用通常更有效
                else:
                    prompt.effectiveness = "Medium"
            
            # 自动语言检测
            if not prompt.language:
                # 检测是否包含中文
                if re.search(r'[\u4e00-\u9fff]', prompt.prompt):
                    prompt.language = "zh"
                # 检测是否包含多种语言
                elif re.search(r'[\u4e00-\u9fff]', prompt.prompt) and re.search(r'[a-zA-Z]', prompt.prompt):
                    prompt.language = "mixed"
                else:
                    prompt.language = "en"
        
        self.stats["labeled_samples"] = labeled_count
        logger.info(f"自动打标签完成: 处理 {labeled_count} 条")
        
        return labeled_count
    
    def split_dataset(
        self,
        train_ratio: float = 0.8,
        val_ratio: float = 0.1,
        test_ratio: float = 0.1,
        stratified: bool = True
    ) -> Dict[str, List[JailbreakPrompt]]:
        """数据集切分
        
        Args:
            train_ratio: 训练集比例
            val_ratio: 验证集比例
            test_ratio: 测试集比例
            stratified: 是否按类别分层采样
            
        Returns:
            切分后的数据集字典
        """
        assert abs(train_ratio + val_ratio + test_ratio - 1.0) < 1e-6, \
            "比例之和必须为1"
        
        logger.info(f"开始数据集切分 (训练:{train_ratio}, 验证:{val_ratio}, 测试:{test_ratio})")
        
        import random
        random.seed(42)  # 设置随机种子保证可复现性
        
        prompts = self.prompts.copy()
        random.shuffle(prompts)
        
        if stratified and len(self.prompts) > 0:
            # 按类别分层切分
            category_prompts: Dict[str, List[JailbreakPrompt]] = defaultdict(list)
            
            for prompt in prompts:
                category_prompts[prompt.category].append(prompt)
            
            train_set: List[JailbreakPrompt] = []
            val_set: List[JailbreakPrompt] = []
            test_set: List[JailbreakPrompt] = []
            
            for category, cat_prompts in category_prompts.items():
                n = len(cat_prompts)
                n_train = max(1, int(n * train_ratio))
                n_val = max(1, int(n * val_ratio))
                
                train_set.extend(cat_prompts[:n_train])
                val_set.extend(cat_prompts[n_train:n_train + n_val])
                test_set.extend(cat_prompts[n_train + n_val:])
            
            random.shuffle(train_set)
            random.shuffle(val_set)
            random.shuffle(test_set)
            
        else:
            # 随机切分
            n = len(prompts)
            n_train = int(n * train_ratio)
            n_val = int(n * val_ratio)
            
            train_set = prompts[:n_train]
            val_set = prompts[n_train:n_train + n_val]
            test_set = prompts[n_train + n_val:]
        
        splits = {
            "train": train_set,
            "val": val_set,
            "test": test_set
        }
        
        logger.info(f"切分完成: 训练集 {len(train_set)}, 验证集 {len(val_set)}, 测试集 {len(test_set)}")
        
        return splits
    
    def export_json(self, filepath: str, data: Any = None) -> None:
        """导出为JSON格式
        
        Args:
            filepath: 输出文件路径
            data: 要导出的数据，默认使用处理后的prompts
        """
        if data is None:
            data = self.prompts
        
        # 转换为字典列表
        if isinstance(data, dict):
            export_data = {
                "export_date": datetime.now().isoformat(),
                "statistics": self.stats,
                "splits": {
                    k: [p.to_dict() for p in v] 
                    for k, v in data.items()
                } if isinstance(data, dict) and "train" in data else data
            }
        elif isinstance(data, list):
            export_data = {
                "export_date": datetime.now().isoformat(),
                "statistics": self.stats,
                "prompts": [p.to_dict() if hasattr(p, 'to_dict') else p for p in data]
            }
        else:
            export_data = data
        
        with open(filepath, 'w', encoding='utf-8') as f:
            json.dump(export_data, f, ensure_ascii=False, indent=2)
        
        logger.info(f"已导出JSON: {filepath}")
    
    def export_csv(self, filepath: str, data: List[JailbreakPrompt] = None) -> None:
        """导出为CSV格式
        
        Args:
            filepath: 输出文件路径
            data: 要导出的数据
        """
        if data is None:
            data = self.prompts
        
        fieldnames = [
            'id', 'name', 'prompt', 'category', 'subcategory',
            'language', 'target', 'complexity', 'effectiveness',
            'source', 'risk_level'
        ]
        
        with open(filepath, 'w', encoding='utf-8-sig', newline='') as f:
            writer = csv.DictWriter(f, fieldnames=fieldnames)
            writer.writeheader()
            
            if TQDM_AVAILABLE:
                iter_data = tqdm(data, desc="  导出CSV", unit="条",
                               bar_format="{l_bar}{bar}| {n_fmt}/{total_fmt} [{elapsed}<{remaining}]")
            else:
                iter_data = data
            
            for prompt in iter_data:
                if hasattr(prompt, 'to_dict'):
                    row = prompt.to_dict()
                else:
                    row = prompt
                writer.writerow(row)
        
        logger.info(f"已导出CSV: {filepath}")
    
    def export_txt(self, filepath: str, data: List[JailbreakPrompt] = None) -> None:
        """导出为纯文本格式
        
        Args:
            filepath: 输出文件路径
            data: 要导出的数据
        """
        if data is None:
            data = self.prompts
        
        with open(filepath, 'w', encoding='utf-8') as f:
            if TQDM_AVAILABLE:
                iter_data = tqdm(list(enumerate(data, 1)), desc="  导出TXT", unit="条",
                               total=len(data), bar_format="{l_bar}{bar}| {n_fmt}/{total_fmt} [{elapsed}<{remaining}]")
            else:
                iter_data = enumerate(data, 1)
            
            for i, prompt in iter_data:
                f.write(f"{'='*60}\n")
                f.write(f"[{i}] {prompt.name} ({prompt.id})\n")
                f.write(f"{'='*60}\n")
                f.write(f"Category: {prompt.category}\n")
                f.write(f"Subcategory: {prompt.subcategory}\n")
                f.write(f"Risk Level: {prompt.risk_level}\n")
                f.write(f"Complexity: {prompt.complexity}\n")
                f.write(f"{'-'*60}\n")
                f.write(f"{prompt.prompt}\n")
                f.write(f"{'-'*60}\n\n")
        
        logger.info(f"已导出TXT: {filepath}")
    
    def generate_report(self) -> Dict[str, Any]:
        """生成预处理报告
        
        Returns:
            包含统计信息的字典
        """
        # 按类别统计
        category_counts = defaultdict(int)
        for prompt in self.prompts:
            category_counts[prompt.category] += 1
        
        # 按风险等级统计
        risk_counts = defaultdict(int)
        for prompt in self.prompts:
            risk_counts[prompt.risk_level] += 1
        
        # 按复杂度统计
        complexity_counts = defaultdict(int)
        for prompt in self.prompts:
            complexity_counts[prompt.complexity] += 1
        
        report = {
            "report_date": datetime.now().isoformat(),
            "input_file": self.input_path,
            "preprocessing_statistics": self.stats,
            "category_distribution": dict(category_counts),
            "risk_level_distribution": dict(risk_counts),
            "complexity_distribution": dict(complexity_counts),
            "total_prompts": len(self.prompts)
        }
        
        return report


def main():
    """主函数"""
    # 记录开始时间
    overall_start_time = time.time()
    
    parser = argparse.ArgumentParser(
        description="越狱提示词数据集预处理脚本",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
示例:
  # 使用默认参数处理原始格式
  python data_preprocess.py
  
  # 处理自定义文件
  python data_preprocess.py --input my_data.json
  
  # 处理RTPB2026格式数据
  python data_preprocess.py --input redteam_prompt_benchmark.json --format rtpb2026
  
  # 指定数据集切分比例
  python data_preprocess.py --split 0.7 0.15 0.15
  
  # 指定输出目录
  python data_preprocess.py --output my_output
  
  # 自定义去重阈值
  python data_preprocess.py --dedup-threshold 0.9

支持的输入格式:
  - original: 原始格式（包含id, name, prompt, category等字段）
  - rtpb2026: RTPB2026格式（包含id, prompt, type, model, source, createdAt字段）
  - auto: 自动检测格式（默认）
        """
    )
    
    parser.add_argument(
        '--input', '-i',
        type=str,
        default='jailbreak_prompts_dataset.json',
        help='输入JSON文件路径 (默认: jailbreak_prompts_dataset.json)'
    )
    
    parser.add_argument(
        '--format', '-f',
        type=str,
        choices=['auto', 'original', 'rtpb2026'],
        default='auto',
        help='输入数据格式 (默认: auto自动检测)'
    )
    
    parser.add_argument(
        '--output', '-o',
        type=str,
        default='output',
        help='输出目录 (默认: output)'
    )
    
    parser.add_argument(
        '--split', '-s',
        type=float,
        nargs=3,
        default=[0.8, 0.1, 0.1],
        help='数据集切分比例 [train val test] (默认: 0.8 0.1 0.1)'
    )
    
    parser.add_argument(
        '--dedup-threshold', '-d',
        type=float,
        default=0.85,
        help='去重相似度阈值 (默认: 0.85)'
    )
    
    parser.add_argument(
        '--no-split',
        action='store_true',
        help='不进行数据集切分'
    )
    
    parser.add_argument(
        '--verbose', '-v',
        action='store_true',
        help='显示详细日志'
    )
    
    args = parser.parse_args()
    
    if args.verbose:
        logging.getLogger().setLevel(logging.DEBUG)
    
    # 打印标题
    print("\n" + "="*60)
    print("🚀 越狱提示词数据集预处理工具")
    print("="*60)
    print(f"📁 输入文件: {args.input}")
    print(f"📋 数据格式: {args.format}")
    print(f"📂 输出目录: {args.output}")
    print(f"🔧 去重阈值: {args.dedup_threshold}")
    if not args.no_split:
        print(f"📊 切分比例: {args.split[0]*100:.0f}% / {args.split[1]*100:.0f}% / {args.split[2]*100:.0f}%")
    print("="*60)
    print()
    
    try:
        # 初始化预处理器
        preprocessor = DatasetPreprocessor(args.input, args.output, args.format)
        
        # ========== 步骤 1: 加载数据 ==========
        step_start = time.time()
        print("📥 [步骤 1/5] 加载数据...")
        preprocessor.load_data()
        step_time = time.time() - step_start
        print(f"   ✅ 完成 (耗时: {step_time:.1f}s)")
        
        # ========== 步骤 2: 去重 ==========
        step_start = time.time()
        print("\n🔄 [步骤 2/5] 去重处理...")
        print(f"   📊 待处理数量: {len(preprocessor.prompts)} 条")
        preprocessor.deduplicate(similarity_threshold=args.dedup_threshold)
        step_time = time.time() - step_start
        print(f"   ✅ 完成 (耗时: {step_time:.1f}s)")
        
        # ========== 步骤 3: 清洗 ==========
        step_start = time.time()
        print(f"\n🧹 [步骤 3/5] 数据清洗...")
        print(f"   📊 待处理数量: {len(preprocessor.prompts)} 条")
        preprocessor.clean()
        step_time = time.time() - step_start
        print(f"   ✅ 完成 (耗时: {step_time:.1f}s)")
        
        # ========== 步骤 4: 自动打标签 ==========
        step_start = time.time()
        print(f"\n🏷️  [步骤 4/5] 自动打标签...")
        print(f"   📊 待处理数量: {len(preprocessor.prompts)} 条")
        preprocessor.auto_label()
        step_time = time.time() - step_start
        print(f"   ✅ 完成 (耗时: {step_time:.1f}s)")
        
        # ========== 步骤 5: 生成报告和导出 ==========
        step_start = time.time()
        print(f"\n💾 [步骤 5/5] 生成报告和导出文件...")
        report = preprocessor.generate_report()
        step_time = time.time() - step_start
        print(f"   ✅ 完成 (耗时: {step_time:.1f}s)")
        
        # 计算总耗时
        overall_time = time.time() - overall_start_time
        
        # 格式化时间输出
        def format_time(seconds):
            if seconds < 60:
                return f"{seconds:.1f}秒"
            elif seconds < 3600:
                mins = int(seconds // 60)
                secs = seconds % 60
                return f"{mins}分{secs:.0f}秒"
            else:
                hours = int(seconds // 3600)
                mins = int((seconds % 3600) // 60)
                return f"{hours}小时{mins}分"
        
        # 输出报告
        print("\n" + "="*60)
        print("📊 预处理报告")
        print("="*60)
        print(f"原始数据量:    {report['preprocessing_statistics']['total_original']}")
        print(f"去重后数量:    {report['preprocessing_statistics']['total_after_dedup']}")
        print(f"清洗后数量:    {report['preprocessing_statistics']['total_after_cleaning']}")
        print(f"移除重复:      {report['preprocessing_statistics']['duplicates_removed']}")
        if args.format == 'rtpb2026' or (args.format == 'auto' and report['preprocessing_statistics']['rtpb2026_converted'] > 0):
            print(f"RTPB2026转换:  {report['preprocessing_statistics']['rtpb2026_converted']} 条")
        print(f"\n类别分布:")
        for cat, count in report['category_distribution'].items():
            print(f"  {cat}: {count}")
        print(f"\n风险等级分布:")
        for risk, count in report['risk_level_distribution'].items():
            print(f"  {risk}: {count}")
        print("="*60 + "\n")
        
        # 导出完整数据集
        print("📦 导出文件...")
        export_start = time.time()
        output_path = os.path.join(args.output, 'processed_dataset.json')
        preprocessor.export_json(output_path)
        preprocessor.export_csv(os.path.join(args.output, 'processed_dataset.csv'))
        preprocessor.export_txt(os.path.join(args.output, 'processed_dataset.txt'))
        export_time = time.time() - export_start
        print(f"   ✅ 导出完成 (耗时: {export_time:.1f}s)")
        
        # 保存报告
        report_path = os.path.join(args.output, 'preprocessing_report.json')
        with open(report_path, 'w', encoding='utf-8') as f:
            json.dump(report, f, ensure_ascii=False, indent=2)
        logger.info(f"已保存报告: {report_path}")
        
        # 数据集切分
        if not args.no_split:
            print("\n📂 数据集切分...")
            split_start = time.time()
            splits = preprocessor.split_dataset(
                train_ratio=args.split[0],
                val_ratio=args.split[1],
                test_ratio=args.split[2]
            )
            
            splits_dir = os.path.join(args.output, 'splits')
            
            # 导出各部分
            for split_name, split_data in splits.items():
                split_prefix = os.path.join(splits_dir, split_name)
                preprocessor.export_json(f"{split_prefix}.json", split_data)
                preprocessor.export_csv(f"{split_prefix}.csv", split_data)
                preprocessor.export_txt(f"{split_prefix}.txt", split_data)
            
            # 保存切分统计
            split_stats = {
                "split_ratios": {
                    "train": args.split[0],
                    "val": args.split[1],
                    "test": args.split[2]
                },
                "split_sizes": {
                    "train": len(splits["train"]),
                    "val": len(splits["val"]),
                    "test": len(splits["test"])
                }
            }
            
            with open(os.path.join(splits_dir, 'split_statistics.json'), 'w', encoding='utf-8') as f:
                json.dump(split_stats, f, ensure_ascii=False, indent=2)
            
            split_time = time.time() - split_start
            print(f"   ✅ 切分完成 (耗时: {split_time:.1f}s)")
        
        # 最终输出
        print("\n" + "="*60)
        print(f"✅ 预处理完成!")
        print(f"⏱️  总耗时: {format_time(overall_time)}")
        print(f"📁 输出目录: {args.output}/")
        print("="*60)
        print("\n输出文件:")
        print("  ├── processed_dataset.json    # 完整处理后数据集")
        print("  ├── processed_dataset.csv     # CSV格式")
        print("  ├── processed_dataset.txt    # 纯文本格式")
        print("  ├── preprocessing_report.json # 预处理报告")
        print("  └── splits/                   # 切分后的数据集")
        print()
        
    except Exception as e:
        logger.error(f"预处理失败: {e}")
        raise


if __name__ == "__main__":
    main()