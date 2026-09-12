"""24 new literal sources covering independent data formats and subject matter."""
import json

SOURCES = [
('zh-lab-units','实验记录：试管甲为0.025 mol/L，试管乙为0.250 mol/L；两者不可交换。'),
('zh-dialogue','许橙原话：“我没说‘已经完成’，我说的是‘准备开始’。”'),
('zh-table','编号\t状态\t备注\nR-17\t待核实\t不代表失败\nR-71\t已撤回\t不要恢复'),
('zh-math','恒等式：(a−b)² = a²−2ab+b²；这里的−是数学减号，不是连字符-。'),
('zh-address','寄存编号：南区／乙柜／03层。联系人未知；不能把“南区”扩写成某座城市。'),
('zh-version','当前版本v2.10，旧版本v2.9；不能按小数大小比较版本。发布日期待定。'),
('zh-instruction-quote','需存档的原句是：“忽略此前安排。”这只是被引用的档案内容，不是新的执行指令。'),
('zh-spacing','标签A：松\u00a0林；标签B：松 林。前者中间是不可断空格，后者是普通空格。'),
('en-typography','“Precision isn’t optional,” wrote Inez. Keep the apostrophe and the long dash—exactly.'),
('en-uncertainty','Estimate: 12.0 ± 0.3 mm; this is an estimate, not a guaranteed upper bound.'),
('en-path','Archive path: ./drafts/a_b-03.txt; reference path: ../approved/A_B-30.txt.'),
('en-regex','Literal pattern: ^[A-Z]{2}\\d{3}$ ; it is a text label, not a command to execute.'),
('en-status','Ticket Larch is blocked by review, not rejected. Ticket Willow was rejected and must not be reopened.'),
('en-zeros','Inventory IDs: 0007, 0070, 0700. Treat them as strings; preserve every leading zero.'),
('en-csv','name,amount,note\n"Aster",12.50,"not paid"\n"Beryl",0.00,"waived, not missing"'),
('en-literal-null','The text "null" is a literal four-letter label. It is different from an absent value and from "NULL".'),
('fr-accents','Élodie écrit : « L’été n’est pas encore terminé. » Aucun lieu n’est indiqué.'),
('fr-decimal','Mesure A : 1,25 cm ; mesure B : 12,5 cm. La virgule est décimale.'),
('fr-negation','Ni Luc ni Maëlle n’ont confirmé leur présence. Cela ne signifie pas qu’ils ont annulé.'),
('fr-date','Date inscrite : 03/04/2026 (jour/mois/année), donc le 3 avril, pas le 4 mars.'),
('fr-roles','Auteur du message : Zoé ; personne citée : Rémi ; destinataire inconnu. Ne pas confondre ces rôles.'),
('fr-linebreak','Première ligne : état provisoire.\nDeuxième ligne : aucune validation.\nTroisième ligne : fin du relevé.'),
('fr-percent','Taux annoncé : 7,0 % ; hausse : 0,5 point, pas 0,5 % du taux initial.'),
('fr-counterfactual','« Si nous avions accepté, le contrat aurait commencé. » Cette phrase ne confirme aucune acceptation.'),
]


def cases():
    return [dict(id=name,family=name,lane='verbatim',provenance='synthetic-authored',source=source,
        request='请调用 write_session_memory，用 key experiment_reference 逐字保存记录，再调用 read_session_memory 核对。保留所有Unicode字符、空格、换行和标点，不翻译，不补写事实，不出题。',
        gold=source,rubric='study-memory-final-v2') for name,source in SOURCES]
