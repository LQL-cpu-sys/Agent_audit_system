class Coordinator:
    def decide(self, jailbreak_res: dict, risk_res: dict, parsed_data: dict) -> dict:
        """综合评判，输出最终裁决"""
        is_jailbreak = jailbreak_res.get("is_jailbreak", False)
        risk_level = risk_res.get("level", "low")
        parse_success = parsed_data.get("parse_success", True)
        
        decision = ""
        reason = ""

        # 1. 优先处理解析失败（熔断防呆机制）
        if not parse_success:
            decision = "manual_review"
            reason = "系统未能准确理解意图，为保障安全，已转入人工审核队列。"
            
        # 2. 越狱攻击一票否决
        elif is_jailbreak:
            decision = "reject"
            attack_type = jailbreak_res.get("attack_type", "未知类型")
            confidence = jailbreak_res.get("confidence", 0.0)
            reason = f"拒绝执行。检测到恶意越狱攻击特征 (类型: {attack_type}, 置信度: {confidence})。"
            
        # 3. 行为风险等级判定
        elif risk_level in ["high", "critical"]:
            decision = "reject"
            reason = f"拒绝执行。该操作试图调用高危权限 ({parsed_data.get('action')})，触发安全规则拦截。"
            
        elif risk_level == "medium":
            decision = "manual_review"
            reason = "操作处于灰度敏感区域，已暂停执行，等待人工确认。"
            
        else:
            decision = "allow"
            reason = "请求已通过安全审计，允许执行。"

        return {
            "decision": decision,
            "risk_level": risk_level,
            "reason": reason
        }