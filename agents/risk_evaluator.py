import json
import os

class RiskEvaluator:
    def __init__(self, config_path: str):
        # 确保能正确找到配置表路径
        if not os.path.exists(config_path):
            raise FileNotFoundError(f"找不到风险配置表：{config_path}")
            
        with open(config_path, 'r', encoding='utf-8') as f:
            self.config = json.load(f)
            
        self.action_map = self.config.get("action_risk_map", {})
        self.sensitive_targets = self.config.get("sensitive_targets_regex", [])

    def evaluate(self, parsed_data: dict) -> dict:
        """评估动作风险，返回评级字典"""
        # 如果解析直接失败了，为了安全直接标为高风险
        if not parsed_data.get("parse_success", True):
            return {"level": "high", "is_sensitive": False}

        action = parsed_data.get("action", "unknown")
        target = str(parsed_data.get("target", ""))
        
        # 1. 查表获取动作的基础风险等级
        base_level = self.action_map.get(action, "medium")
        
        # 2. 检测目标是否触碰敏感黑名单（简单的字符串包含检查）
        is_sensitive = False
        for sensitive_keyword in self.sensitive_targets:
            if sensitive_keyword in target:
                is_sensitive = True
                break
                
        # 3. 风险升级逻辑
        if is_sensitive:
            return {"level": "critical", "is_sensitive": True}
            
        return {"level": base_level, "is_sensitive": False}