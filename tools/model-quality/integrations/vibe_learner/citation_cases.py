"""24 independently authored synthetic source/question pairs; development only."""
import json

# Separate topics and mechanisms, not renamed copies of one fact.
ROWS = [
('en-mass','The brass cube has a mass of 42 grams. The wooden cube has a mass of 18 grams.','What is the brass cube mass in grams? Return only the number.', '42',True),
('en-valve','The Lumen valve was inspected. It was not opened; it remains closed.','What is the Lumen valve state? Use opened or closed.', 'closed',True),
('en-route','Route Cedar passes through the tunnel. Route Aspen ends before the tunnel.','Which route passes through the tunnel? Return its name.', 'Cedar',True),
('en-delay','The beacon flashes every 9 seconds; the first flash is immediate.','How many seconds separate successive beacon flashes?', '9',True),
('en-art','This note explains how to rinse glassware with distilled water after a titration.','What year was the painting Night Harbor completed? The current note is unrelated.', 'unknown',False),
('en-founder','A binary tree node has at most two children. A leaf has no children.','Who founded the town of Amberwick? The current note is unrelated.', 'unknown',False),
('en-substring','The scanner records fluorescence spectra at three wavelengths.','What does an unpaid invoice for rent total? The current note is unrelated.', 'unknown',False),
('en-nothing','The copper conductor carries a measured current of two amperes.','When did the fictional ship Verity depart? The current note is unrelated.', 'unknown',False),
('zh-color','样品松石在加热前是蓝色，加热后变为白色。冷却不改变白色状态。','样品松石加热后的颜色是什么？用white或blue表示。','white',True),
('zh-negative','装置青禾的警报没有开启。指示灯闪烁不代表警报开启。','装置青禾的警报当前开启了吗？用on或off表示。','off',True),
('zh-compare','盒子甲有七枚圆片，盒子乙有十二枚圆片。甲乙没有交换圆片。','盒子乙共有多少枚圆片？用阿拉伯数字。','12',True),
('zh-meaning','记录标注状态为“待审核”，并不表示已经通过审核。只有状态“通过”才可出库。','当前记录是否可以出库？用yes或no。','no',True),
('zh-author','植物根毛增加根部与土壤的接触面积，有助于吸收水分。','小说远山灯塔的作者是谁？当前教材与该问题无关。','unknown',False),
('zh-place','等式两边同时减去相同的数，等式仍然成立。','青岚博物馆位于哪个城市？当前教材与该问题无关。','unknown',False),
('zh-date','月球表面没有液态海洋，环形山来自撞击等地质过程。','虚构乐队纸船第一次演出的日期是什么？当前教材与该问题无关。','unknown',False),
('zh-price','淀粉遇碘液会显蓝色，这是检测淀粉的一种方法。','风铃书店今天的会员卡售价是多少？当前教材与该问题无关。','unknown',False),
('fr-temperature','Le bain est maintenu à 24 degrés. La sonde externe indique 19 degrés.','Quelle est la température du bain en degrés ? Réponds par un nombre.','24',True),
('fr-negation','La boîte Rubis est vide. La boîte Jade contient les trois clés.','Quelle boîte contient les clés ? Donne son nom.','Jade',True),
('fr-sequence','Pour cette expérience, on filtre le mélange avant de le chauffer.','Quelle action vient avant le chauffage ? Utilise filtration ou refroidissement.','filtration',True),
('fr-permission','Le badge orange autorise la salle A seulement. Il ne permet pas la salle B.','Le badge orange autorise-t-il la salle B ? Utilise yes ou no.','no',True),
('fr-history','Une fraction représente une partie d\'un ensemble. Le dénominateur compte les parts égales.','Qui a construit le pont fictif Valdor ? Cette source est sans rapport.','unknown',False),
('fr-time','Le sel se dissout dans l\'eau; le sable reste visible au fond du récipient.','À quelle heure ouvre le cinéma fictif Aurore ? Cette source est sans rapport.','unknown',False),
('fr-person','Les racines transportent de l\'eau vers les feuilles par le xylème.','Qui est le capitaine du navire fictif Merle ? Cette source est sans rapport.','unknown',False),
('fr-cost','Le triangle rectangle possède un angle droit. Ses deux autres angles sont aigus.','Quel est le prix du billet pour le festival fictif Nuage ? Cette source est sans rapport.','unknown',False),
]


def cases():
    return [dict(id=identifier,family=identifier,lane='citation',provenance='synthetic-authored',
        source=json.dumps({'text':source,'relevant':relevant,'language':identifier[:2]},ensure_ascii=False),
        request=question+'\n只根据相关教材事实回答；来源不相关或未提供答案时使用unknown。仅返回一个JSON对象，唯一字段answer为字符串，不加其他文字。',
        gold=json.dumps({'answer':answer},ensure_ascii=False),rubric='citation-facts-v1')
        for identifier,source,question,answer,relevant in ROWS]
