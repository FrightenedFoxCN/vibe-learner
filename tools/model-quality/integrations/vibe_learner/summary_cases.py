"""Small separate fact-summary matrix; no character-exact scoring of summaries."""
import json

ROWS=[
('summary-cancel', '周岚原定2026-08-09参加陶艺课，后来取消，没有补报其他日期。陶艺教室地点尚未公布。', {'person':'周岚','status':'cancelled','current_date':'unknown','place':'unknown'}),
('summary-effective', '通知于2026-04-03录入。工作坊从2026-05-01起改在东厅举行；西厅是旧地点。没有其他变更。', {'effective_date':'2026-05-01','venue':'东厅'}),
('summary-quote', '宋弦转述何璟的话：何璟也许参加圆桌讨论，目前没有确认。宋弦本人不参加。', {'tentative_person':'何璟','absent_person':'宋弦'}),
('summary-dates', 'The seal was replaced on 2026-03-12. The report was filed on 2026-03-15. No technician name was recorded.', {'replaced_on':'2026-03-12','filed_on':'2026-03-15','technician':'unknown'}),
('summary-ownership', 'Priya owns the silver compass. She lent it to Owen for a week; Owen did not buy it. The loan return date is unspecified.', {'owner':'Priya','borrower':'Owen','return_date':'unknown'}),
('summary-negation', 'The Fern shipment was delayed, not cancelled. The next delivery date has not been announced. Its contents remain unchanged.', {'status':'delayed','delivery_date':'unknown'}),
('summary-fr-state', 'Le dossier Quartz a été archivé, puis réactivé le 2026-06-20. La date de publication reste inconnue.', {'status':'active','reactivated_on':'2026-06-20','publication':'unknown'}),
('summary-fr-roles', 'Nina a écrit le message. Elle rapporte que Louis a refusé la proposition; elle ne dit rien sur sa propre décision.', {'author':'Nina','refused_person':'Louis','author_decision':'unknown'}),
]


FIELD_MEANINGS = {
    'person':'原话中的人物姓名，仅写姓名并原样保留',
    'status':'当前状态：只用active、archived、inactive、cancelled或delayed中的一个',
    'current_date':'当前有效的新安排日期；旧安排已取消且没有新日期时必须为unknown',
    'place':'当前公布的地点，没有公布时为unknown',
    'effective_date':'变更实际生效日期，不是通知录入日期',
    'venue':'变更生效后的地点名称，仅写名称',
    'tentative_person':'尚未确认是否参加的人物姓名，仅写原文姓名',
    'absent_person':'明确不参加的人物姓名，仅写原文姓名',
    'replaced_on':'更换实际发生日期',
    'filed_on':'报告提交日期',
    'technician':'记录中明确的技术员姓名，没有记录时为unknown',
    'owner':'当前所有者姓名，不是借用者，仅写原文姓名',
    'borrower':'当前借用者姓名，仅写原文姓名',
    'return_date':'明确约定的归还日期，未约定具体日期时为unknown',
    'delivery_date':'已经公布的下一次送达日期，没有公布时为unknown',
    'reactivated_on':'重新启用发生日期',
    'publication':'公布的发布日期，没有公布时为unknown',
    'author':'消息作者姓名，仅写原文姓名',
    'refused_person':'明确拒绝提议的人物姓名，仅写原文姓名',
    'author_decision':'作者本人对提议的决定，原话没有说明时为unknown',
}


def cases():
    return [dict(id=name,family=name,lane='summary',provenance='synthetic-authored',source=source,
        request='请调用write_session_memory，以key experiment_reference保存这段记录的事实摘要，再调用read_session_memory核对。content必须是JSON对象的字符串，只含这些字段：'+','.join(gold)+'。字段定义：'+ '; '.join(key+'='+FIELD_MEANINGS[key] for key in gold)+'。所有字段值使用字符串；未知值写unknown；状态字段用英文小写标签，不要加入原话没有的事实。',
        gold=json.dumps(gold,ensure_ascii=False),rubric='study-memory-facts-v1') for name,source,gold in ROWS]
