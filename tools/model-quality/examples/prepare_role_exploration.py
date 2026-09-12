import argparse,json
from pathlib import Path
p=argparse.ArgumentParser();p.add_argument('--budget-from',type=Path,required=True);p.add_argument('--output',type=Path,required=True);args=p.parse_args()
rows=[
('plan-pages','Physical PDF page 1 is the cover marked roman i. Physical page 2 is printed page 17: solve 3x+5=20 by subtracting 5 then dividing by 3. Physical page 3 is printed page 18: verify by substitution. Available time: 18 minutes.',
 'Plan exactly 3 activities totaling 18 minutes. facts keys: solution (number alone), equation_physical_page, equation_printed_page (page numbers alone). learner_prompt asks a new practice question without giving its answer.',{'solution':'5','equation_physical_page':'2','equation_printed_page':'17'},18,3,[]),
('plan-scope','Lesson source: a bag contains 3 red and 2 blue balls, one draw. P(red)=3/5. Replacement is outside this lesson. The learner has 17 minutes; reading must not consume the whole session.',
 'Plan exactly 3 positive-duration activities totaling 17 minutes. facts keys: red_probability (fraction), ball_total (number), replacement_scope (exactly outside). Ask the learner to justify a probability.',{'red_probability':'3/5','ball_total':'5','replacement_scope':'outside'},17,3,[]),
('media-chart','Chart data, synthetic: labels A,B,C correspond to values 4,9,6. The bars are positioned left, center, right. Color is decorative and not a category. Available time 11 minutes.',
 'Create 2 activities totaling 11 minutes and a chart-reading learner prompt. facts keys: maximum_label (letter), maximum_position (left/center/right), maximum_value (number), C_minus_A (number).',{'maximum_label':'B','maximum_position':'center','maximum_value':'9','C_minus_A':'2'},11,2,[]),
('media-question','Teacher-only specification: assess 6×7; correct answer 42. Before submission, do not reveal the answer, an answer key, a worked solution or the words forty-two. Give one practice activity for 5 minutes.',
 'Produce exactly one 5-minute activity. facts is server-side in this experiment: keys answer (number), kind (exactly fill_blank). learner_prompt is the public pre-submission fill-in question; never include the answer.',{'answer':'42','kind':'fill_blank'},5,1,['42','forty-two','四十二'])]
cases=[dict(id=i,family=i,lane='roles',provenance='synthetic-authored',source=s,request=r,gold=json.dumps(dict(facts=f,minutes=m,activity_count=n,forbidden=b)),rubric='role-exact-v1') for i,s,r,f,m,n,b in rows]
for case in cases:
    if case['id']=='media-chart':
        case['source']+='\nCHART_SOURCE_JSON:\n'+json.dumps({'kind':'bar-chart-source-v1','labels':['A','B','C'],'values':[4,9,6]})
        case['source']+='\nCHART_QUESTION_REQUIREMENTS_JSON:\n'+json.dumps([{'operation':'maximum','labels':['A','B','C']},{'operation':'difference','labels':['C','A']}])
        case['request']+=' Include chart_questions with maximum over labels [A,B,C] and difference for labels [C,A]. The application renders these questions alongside a real chart; learner_prompt remains a proposal and is not the delivered chart question.'
manifest=dict(version='quality-campaign-v1',id='m3-role-exploration-20260912-v1',purpose='Explore separate same-model generator, reviewer, reviser calls versus a single generator; proposal-only development experiment.',transport='minimax',adapter='vibe_learner.role_exploration:run_sample',concurrency=4,seed=912,repetitions=1,timeout_seconds=60,sample_deadline_seconds=600,sample_wire_limit=3,max_output_tokens=4096,input_reservation_tokens=100000,thinking='adaptive',temperature=0.1,budget=json.loads(args.budget_from.read_text())['budget'],cases=cases,variants=[dict(id='baseline',instruction='One generation'),dict(id='review-revise',instruction='Generate, separately review, revise'),dict(id='self-revise',instruction='Generate and self-revise twice; matched three-call control')])
args.output.write_text(json.dumps(manifest,ensure_ascii=False,indent=2)+'\n')
