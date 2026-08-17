"""Context-aware product scope checks for downstream planning artifacts."""

from __future__ import annotations

import re
from dataclasses import dataclass, field
from typing import Any


@dataclass(frozen=True)
class ProductConcept:
    label: str
    terms: tuple[str, ...]
    description: str


@dataclass
class ProductScopeResult:
    passed: bool
    allowed_concepts: list[str] = field(default_factory=list)
    candidate_concepts: list[str] = field(default_factory=list)
    unsupported_concepts: list[str] = field(default_factory=list)


PRODUCT_CONCEPTS: tuple[ProductConcept, ...] = (
    ProductConcept("coupon", ("coupon", "coupons", "promo code", "优惠券"), "coupon or promo-code capability"),
    ProductConcept("discount", ("discount", "discounts", "promotion", "promotions", "折扣", "促销"), "discount or promotion capability"),
    ProductConcept("loyalty_program", ("loyalty program", "loyalty points", "loyalty rewards", "积分计划", "忠诚度计划"), "loyalty program"),
    ProductConcept("membership_tier", ("membership tier", "membership tiers", "tiered membership", "会员等级"), "membership tiering"),
    ProductConcept("payment_gateway", ("payment gateway", "payment processor", "checkout", "card declined"), "payment gateway behavior"),
    ProductConcept("ai_chatbot", ("ai chatbot", "chatbot", "support bot", "ai support"), "AI chatbot or support bot"),
    ProductConcept("referral_program", ("referral program", "referral", "invite rewards"), "referral program"),
    ProductConcept("reward_system", ("reward system", "reward points", "rewards program", "奖励系统", "奖励计划"), "reward system"),
    ProductConcept("refund", ("refund", "refunds", "退款"), "refund handling"),
    ProductConcept("technical_api", ("api", "endpoint", "database", "sql", "react", "vue"), "technical implementation detail"),
)


def extract_allowed_product_concepts(*sources: Any) -> list[str]:
    """Return high-risk product concepts explicitly present in upstream sources."""
    text = _flatten_text(sources)
    return sorted(_concepts_in_text(text))


def validate_product_scope(candidate: Any, *allowed_sources: Any) -> ProductScopeResult:
    """Fail only when a high-risk concept appears without upstream support.

    The check is deterministic and format-only: it does not infer missing
    product meaning or rewrite outputs. A concept is allowed when the same
    concept is explicitly present in Requirement/Finding/AC source text.
    """
    candidate_text = _flatten_text((candidate,))
    allowed_text = _flatten_text(allowed_sources)
    candidate_concepts = _concepts_in_text(candidate_text)
    allowed_concepts = _concepts_in_text(allowed_text)
    unsupported = sorted(candidate_concepts - allowed_concepts)
    return ProductScopeResult(
        passed=not unsupported,
        allowed_concepts=sorted(allowed_concepts),
        candidate_concepts=sorted(candidate_concepts),
        unsupported_concepts=unsupported,
    )


def _concepts_in_text(value: str) -> set[str]:
    normalized = value.casefold()
    return {
        concept.label
        for concept in PRODUCT_CONCEPTS
        if any(_contains_term(normalized, term.casefold()) for term in concept.terms)
    }


def _contains_term(text: str, term: str) -> bool:
    if not term:
        return False
    if _is_ascii_term(term):
        return re.search(rf"(?<![a-z0-9]){re.escape(term)}(?![a-z0-9])", text) is not None
    return term in text


def _flatten_text(value: Any) -> str:
    parts: list[str] = []

    def visit(item: Any) -> None:
        if isinstance(item, str):
            parts.append(item)
        elif isinstance(item, dict):
            for nested in item.values():
                visit(nested)
        elif isinstance(item, (list, tuple, set)):
            for nested in item:
                visit(nested)
        elif item is not None:
            parts.append(str(item))

    visit(value)
    return " ".join(parts)


def _is_ascii_term(term: str) -> bool:
    try:
        term.encode("ascii")
    except UnicodeEncodeError:
        return False
    return True
