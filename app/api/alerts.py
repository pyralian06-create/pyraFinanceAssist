"""
盯盘告警规则管理 API

对应 /api/alerts/* 路由
"""

from fastapi import APIRouter, Depends, HTTPException, Query, status
from fastapi.responses import Response
from sqlalchemy.orm import Session
from typing import Optional, List

from app.models.database import get_db
from app.models.alert_rule import AlertRule
from app.schemas.alert import AlertRuleCreate, AlertRuleResponse, AlertRuleUpdate, AlertRuleToggle

router = APIRouter()


@router.post("/", response_model=AlertRuleResponse, status_code=status.HTTP_201_CREATED)
@router.post("", response_model=AlertRuleResponse, status_code=status.HTTP_201_CREATED)  # 支持不带斜杠
def create_alert_rule(
    rule: AlertRuleCreate,
    db: Session = Depends(get_db)
):
    """
    创建盯盘告警规则

    监控指标说明：
    - PRICE: 价格（单位：人民币或相应货币）
    - VOLUME: 成交量（单位：手或份）
    - CHANGE_PCT: 涨跌幅（单位：百分比 %）

    运算符说明：
    - '>': 大于
    - '<': 小于
    - '>=': 大于等于
    - '<=': 小于等于

    示例请求体（贵州茅台跌破 1500 元时告警）：
    ```json
    {
        "asset_type": "STOCK_A",
        "symbol": "sh600519",
        "metric": "PRICE",
        "operator": "<",
        "threshold": 1500,
        "description": "贵州茅台跌破 1500"
    }
    ```
    """
    db_rule = AlertRule(
        asset_type=rule.asset_type.upper(),
        symbol=rule.symbol,
        metric=rule.metric.upper(),
        operator=rule.operator,
        threshold=rule.threshold,
        description=rule.description,
        is_active=True  # 新规则默认启用
    )
    db.add(db_rule)
    db.commit()
    db.refresh(db_rule)
    return db_rule


@router.get("/", response_model=List[AlertRuleResponse])
@router.get("", response_model=List[AlertRuleResponse])  # 支持不带斜杠
def list_alert_rules(
    is_active: Optional[bool] = Query(None, description="按启用状态过滤: true=启用, false=禁用"),
    db: Session = Depends(get_db)
):
    """
    查询告警规则列表

    支持按启用状态过滤：
    - GET /api/alerts 或 /api/alerts/ — 全部规则
    - GET /api/alerts?is_active=true — 仅启用的规则
    - GET /api/alerts?is_active=false — 仅禁用的规则
    """
    query = db.query(AlertRule).order_by(AlertRule.created_at.desc())

    if is_active is not None:
        query = query.filter(AlertRule.is_active == is_active)

    return query.all()


@router.get("/{alert_id}", response_model=AlertRuleResponse)
def get_alert_rule(
    alert_id: int,
    db: Session = Depends(get_db)
):
    """获取单条告警规则"""
    rule = db.query(AlertRule).filter(AlertRule.id == alert_id).first()
    if not rule:
        raise HTTPException(status_code=404, detail=f"告警规则 {alert_id} 不存在")
    return rule


@router.patch("/{alert_id}", response_model=AlertRuleResponse)
def update_alert_rule(
    alert_id: int,
    rule_update: AlertRuleUpdate,
    db: Session = Depends(get_db)
):
    """
    部分更新告警规则

    支持修改以下字段：
    - metric: 监控指标
    - operator: 比较运算符
    - threshold: 触发阈值
    - description: 规则描述
    - is_active: 启用/禁用

    示例：调整触发阈值
    ```json
    {"threshold": 1450}
    ```
    """
    rule = db.query(AlertRule).filter(AlertRule.id == alert_id).first()
    if not rule:
        raise HTTPException(status_code=404, detail=f"告警规则 {alert_id} 不存在")

    # 只更新非 None 字段
    update_data = rule_update.model_dump(exclude_unset=True)
    for field, value in update_data.items():
        if value is not None:
            setattr(rule, field, value)

    db.commit()
    db.refresh(rule)
    return rule


@router.patch("/{alert_id}/toggle", response_model=AlertRuleResponse)
def toggle_alert_rule(
    alert_id: int,
    toggle: AlertRuleToggle,
    db: Session = Depends(get_db)
):
    """
    快速启用/禁用告警规则

    便捷接口：从看板 UI 上的开关按钮调用

    示例：禁用规则
    ```json
    {"is_active": false}
    ```
    """
    rule = db.query(AlertRule).filter(AlertRule.id == alert_id).first()
    if not rule:
        raise HTTPException(status_code=404, detail=f"告警规则 {alert_id} 不存在")

    rule.is_active = toggle.is_active
    db.commit()
    db.refresh(rule)
    return rule


@router.delete("/{alert_id}", status_code=status.HTTP_204_NO_CONTENT)
def delete_alert_rule(
    alert_id: int,
    db: Session = Depends(get_db)
):
    """
    删除告警规则

    删除后无法恢复
    """
    rule = db.query(AlertRule).filter(AlertRule.id == alert_id).first()
    if not rule:
        raise HTTPException(status_code=404, detail=f"告警规则 {alert_id} 不存在")

    db.delete(rule)
    db.commit()
    return Response(status_code=status.HTTP_204_NO_CONTENT)
