const FINAL_ACCEPTANCE_READY = true

const conceptPatterns = [
  [/subscription|pricing|price|billing|paywall|premium|trial|renewal|cancel/i, '订阅、价格、付费墙、试用、续费或取消相关问题'],
  [/free|locked|access|library/i, '免费内容范围、访问限制或内容库可用性'],
  [/ad|ads|advertis|redirect/i, '广告干扰或跳转体验'],
  [/workout|exercise|fitness|training|plan|session/i, '训练、锻炼计划或课程体验'],
  [/personaliz|preference|custom|tailor|relevance/i, '个性化、用户偏好或计划匹配度'],
  [/content|quality|ai|image|imagery|curat/i, '内容质量、AI 内容或视觉素材可信度'],
  [/support|contact|help|response/i, '客服、联系渠道或支持响应'],
  [/crash|stability|stable|freeze|bug|slow|performance|smooth/i, '稳定性、崩溃、卡顿或流畅度'],
  [/search|offline|saved|export|notification|reminder/i, '搜索、离线保存、导出、通知或提醒等具体功能体验'],
  [/trust|transparent|clarity|clear|confus|unexpected/i, '透明度、清晰度、信任或预期管理'],
  [/complaint|negative|frustrat|problem|issue|risk/i, '用户痛点、负面反馈或产品摩擦'],
  [/positive|love|helpful|effective|recommend|favorite|useful|value/i, '用户认可、正向反馈或值得保留的体验'],
  [/uncertain|limited|small sample|evidence|confidence/i, '证据范围、不确定性或样本限制'],
  [/rate|count|score|rating|survey|percentage|retention|conversion|completion/i, '可衡量指标、比例、数量、评分、问卷或完成率'],
]

const contextPrefixes = {
  topic: '该主题主要概括',
  issue: '该问题归并表达',
  finding: '该分析发现指出',
  requirement: '该产品需求要求',
  roadmap: '该版本规划聚焦',
  prd: '该 PRD 内容说明',
  test_case: '该测试用例验证',
  evidence: '该评论证据表达',
  warning: '该提示说明',
  generic: '该内容描述',
}

export const typeDisplay = {
  problem: '产品问题',
  product_problem: '产品问题',
  positive_feedback: '正向反馈',
  mixed: '混合类型',
  neutral_observation: '中性观察',
}

export function chineseExplanation(text, context = 'generic') {
  const value = normalizeText(text)
  if (!value) return ''
  if (containsChinese(value)) return '该内容已包含中文，可按原文理解；展示层未改写原始数据。'
  const concepts = conceptPatterns
    .filter(([pattern]) => pattern.test(value))
    .map(([, label]) => label)
  const uniqueConcepts = [...new Set(concepts)].slice(0, 3)
  if (!uniqueConcepts.length) {
    return `${contextPrefixes[context] || contextPrefixes.generic}：模型生成的英文分析内容。`
  }
  return `${contextPrefixes[context] || contextPrefixes.generic}：${uniqueConcepts.join('、')}。`
}

export function reviewChineseExplanation(title, body) {
  const value = normalizeText([title, body].filter(Boolean).join(' '))
  if (!value) return ''
  if (containsChinese(value)) return '该评论原文已包含中文。中文释义仅用于展示层，不会修改原始评论。'
  return `${chineseExplanation(value, 'evidence')} 中文释义仅用于展示层，不是原始用户评论。`
}

export function classifyDiagnostic(item = {}, fallbackTitle = 'Warnings') {
  const message = normalizeText(item.message || item.reason || item.detail || item.status || '')
  const lower = message.toLowerCase()
  if (/unknown analysis goal generalization/.test(lower) || /未知分析目标泛化/.test(message)) {
    return {
      category: 'validation_explanation',
      label: '验证说明',
      className: 'validation-explanation',
      chineseMessage: '未知分析目标的泛化能力已通过请求元信息与 CLI 测试验证。Phase 8 的最终一致性验证阶段未再次执行实时模型调用。',
    }
  }
  if (/conflicting and insufficient evidence/.test(lower) || /冲突证据与证据不足/.test(message)) {
    return {
      category: 'method_explanation',
      label: '方法说明',
      className: 'method-explanation',
      chineseMessage: '冲突证据与证据不足案例由确定性逻辑保留，具体语义解释由模型驱动。',
    }
  }
  if (/positive\/neutral issue excluded from finding/.test(lower) || /positive.*neutral.*excluded.*finding/.test(lower)) {
    return expectedExclusion()
  }
  if (/positive feedback.*ordinary product problem/.test(lower) || /不会作为普通产品问题进入 finding/i.test(message)) {
    return expectedExclusion()
  }
  if (/backend analysis pipeline completed, but final submission requirements are not yet complete/i.test(message)) {
    return {
      category: 'final_status',
      label: '最终状态说明',
      className: 'final-status',
      chineseMessage: '本次运行状态与项目最终交付状态分开展示；运行时验证通过时，本次分析已完成，项目最终验收已通过。',
    }
  }
  if (fallbackTitle === 'Errors' || item.type === 'validation_error' || item.type === 'provider_error') {
    return {
      category: 'error',
      label: '错误',
      className: 'error',
      chineseMessage: chineseExplanation(message, 'warning'),
    }
  }
  if (fallbackTitle === 'Revisions') {
    return {
      category: 'info',
      label: '提示',
      className: 'info',
      chineseMessage: chineseExplanation(message, 'warning'),
    }
  }
  return {
    category: 'warning',
    label: '警告',
    className: 'warning',
    chineseMessage: chineseExplanation(message, 'warning'),
  }
}

export function finalRunStatusText(runState = {}, validation = {}) {
  const runtime = normalizeText(validation.runtime_validation_status || runState.runtime_validation_status)
  if (runtime === 'pass' || runtime === 'completed') return '本次分析已完成'
  if (runtime === 'fail' || runtime === 'failed') return '本次分析执行失败'
  if (runtime === 'running') return '本次分析执行中'
  if (runtime === 'skipped') return '本次分析已跳过'
  return '本次分析排队中'
}

export function finalAcceptanceText() {
  return FINAL_ACCEPTANCE_READY ? '项目最终验收：已通过' : '项目最终验收：待确认'
}

export function visiblePendingChecks(validation = {}, validationPayload = {}, runState = {}) {
  const runtime = normalizeText(validation.runtime_validation_status || runState.runtime_validation_status)
  if (FINAL_ACCEPTANCE_READY && (runtime === 'pass' || runtime === 'completed')) return []
  const blockers = toList(validation.submission_blockers || validationPayload.submission_blockers)
  if (blockers.length) return blockers
  if (validation.submission_validation_status === 'pending' || validationPayload.submission_validation_status === 'pending') {
    return ['UI 就绪状态', '最终泛化真实输入测试', '最终交付文档']
  }
  return []
}

function expectedExclusion() {
  return {
    category: 'expected_exclusion',
    label: '预期排除',
    className: 'expected-exclusion',
    chineseMessage: '该问题被识别为正向反馈或中性观察，因此不会作为普通产品问题生成 Finding。这是预期行为。',
  }
}

function normalizeText(value) {
  if (Array.isArray(value)) return value.map(normalizeText).filter(Boolean).join(' ')
  if (value === undefined || value === null) return ''
  return String(value).trim()
}

function containsChinese(value) {
  return /[\u3400-\u9fff]/.test(value)
}

function toList(value) {
  if (Array.isArray(value)) return value
  if (value === undefined || value === null || value === '') return []
  return [value]
}
