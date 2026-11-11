"""Fresh final G1 cohort, fixed before worker feedback.

The earlier j cohort is retired after its partial run. These k inputs have not
been submitted to either worker. Freeze the application before their first use.
"""
import copy

FROZEN_SOURCE_SHA256='324a9aec69a4534842f33b062dc85ef6c6470ac58be1ac75a98d8acac816b86e'
FROZEN_LOCAL_SOURCE_SHA256='9ee64dcc8f768882aaa765b42f4657c0afe06f2841ff2228c9a9ca827258bfb3'


def fresh_cases():
    rows=[]
    def region(x1,x2,y1,y2,z1,z2):return dict(x1=x1,x2=x2,y1=y1,y2=y2,z1=z1,z2=z2)
    def build(op,r,block):return dict(operation=op,region=r,block=block)
    def clear(r,**extra):return dict(operation='clear',region=r,clear_blocks=['dirt'],**extra)
    def add(group,turns,expected,**extra):
        index=sum(c['group']==group for c in rows)+1
        rows.append(dict(id=f'k{group+1}-{index}',group=group,split='holdout',turns=turns,
                         expected=expected,reference=None,**extra))
    def pointer(x,z):
        return dict(selection_id='55555555-5555-4555-8555-555555555555',source='owner_pointer',
            points=[dict(x=x,y=64,z=z,block='grass_block',face=[0,1,0]),
                    dict(x=x+2,y=64,z=z+1,block='grass_block',face=[0,1,0])])

    add(0,['上限Y=64、X=-29〜-27、Z=26〜27で、地面Y=62を残し、土と石だけ除去して整地してください。'],
        dict(operation='level',level=dict(x1=-29,x2=-27,z1=26,z2=27,ground_y=62,top_y=64),clear_blocks=['dirt','stone']))
    add(0,['Ｙ=65、Ｚ=-29〜-27、Ｘ=24〜26に、オークの板材の床を敷いてください。'],
        build('floor',region(24,26,65,65,-29,-27),'oak_planks'))
    add(0,['Z=28の一面に、X=-29〜-26、Y=65〜67で丸石の壁を建ててください。'],
        build('wall',region(-29,-26,65,67,28,28),'cobblestone'))
    add(0,['X=26〜27、Z=-30〜-29、Y=60〜62の穴を石で埋め戻してください。'],
        build('backfill',region(26,27,60,62,-30,-29),'stone'))

    add(1,['X=-28〜-26、Z=24〜26にオークの板材の床を敷いてください。','仕上げの高さはY=65です。'],
        build('floor',region(-28,-26,65,65,24,26),'oak_planks'),expect_question=True)
    add(1,['Y=65、X=25〜27、Z=-28〜-26に床を敷いてください。','材料は石です。'],
        build('floor',region(25,27,65,65,-28,-26),'stone'),expect_question=True)
    add(1,['X=-28〜-25、Y=65〜67にガラスの壁を建ててください。','壁の面はZ=25です。'],
        build('wall',region(-28,-25,65,67,25,25),'glass'),expect_question=True)
    add(1,['X=24〜25、Z=-29〜-28の穴を土で埋め戻してほしいです。','底から上端はY=60〜62です。'],
        build('backfill',region(24,25,60,62,-29,-28),'dirt'),expect_question=True)

    add(2,['X=-30〜-28、Y=65、Z=22〜24、いやZ=23〜25に石の床を敷いてください。',
           '最終指定はX=-30〜-28、Y=65、Z=23〜25です。石の床を敷いてください。'],
        build('floor',region(-30,-28,65,65,23,25),'stone'),expect_question=True)
    add(2,['X=24〜25、Y=65、Z=-30〜-29に3×3のガラスの床を敷いてください。',
           'X=24〜25、Y=65、Z=-30〜-29に2×2のガラスの床を敷いてください。'],
        {**build('floor',region(24,25,65,65,-30,-29),'glass'),'expected_dimensions':[2,2]},
        clarify_first_prepare=True,expect_question=True)
    add(2,['X=-27〜-25、Y=65、Z=26〜28、いや66にオークの板材の床を敷いてください。',
           'X=-27〜-25、Y=66、Z=26〜28にオークの板材の床を敷いてください。'],
        build('floor',region(-27,-25,66,66,26,28),'oak_planks'),expect_question=True)
    add(2,['X=27〜28、Y=65、Z=-27〜-26に3×3の丸石の床を敷いてください。',
           'X=27〜28、Y=65、Z=-27〜-26に2×2の丸石の床を敷いてください。'],
        {**build('floor',region(27,28,65,65,-27,-26),'cobblestone'),'expected_dimensions':[2,2]},
        clarify_first_prepare=True,expect_question=True)

    add(3,['X=-30〜-28、Y=65〜66、Z=20〜21の土を除去しないでください。'],None)
    add(3,['X=26〜28、Y=65、Z=-30〜-28に石の床を作れますか？まだ実行しないでください。'],None)
    add(3,['『X=-29〜-26、Y=65〜67、Z=24にガラスの壁を建ててください』は架空の例文です。実行せず文章を説明してください。'],None)
    add(3,['X=25〜26、Y=60〜62、Z=-30〜-29の穴を土で埋め戻さないでください。'],None)

    ref=pointer(-27,22)
    add(4,['X=27〜29、Y=65、Z=-29〜-27にガラスの床を敷いてください。'],
        build('floor',region(27,29,65,65,-29,-27),'glass'))
    rows[-1]['reference']=copy.deepcopy(ref)
    add(4,['指示棒で選んだ地面の二つの角の上に、丸石で床を敷いてください。'],
        dict(operation='floor',selection_id=ref['selection_id'],block='cobblestone'),change_reference_after_select=True)
    rows[-1]['reference']=copy.deepcopy(ref)
    add(4,['指示棒で選んだ地面の2点の上に、石の床を敷いてください。'],
        dict(operation='floor',selection_id=ref['selection_id'],block='stone'),refusal='selection_expired')
    rows[-1]['reference']=copy.deepcopy(ref)
    add(4,['選んだ2点のX/Z範囲を、地面Y=64を残し上限Y=66まで、土と石だけ除去して整地してください。'],
        dict(operation='level',selection_id=ref['selection_id'],level=dict(ground_y=64,top_y=66),clear_blocks=['dirt','stone']))
    rows[-1]['reference']=copy.deepcopy(ref)

    r=region(-28,-26,65,66,26,27)
    add(5,['X=-28〜-26、Y=65〜66、Z=26〜27の土を除去し、地面Y=64は保護して残してください。'],
        clear(r,preserve_regions=[region(-28,-26,64,64,26,27)]))
    r=region(25,27,65,65,-29,-28)
    add(5,['X=25〜27、Y=65、Z=-29〜-28の土だけ除去してください。地面Y=64は残してください。'],
        clear(r,preserve_regions=[region(25,27,64,64,-29,-28)]),refusal='protected_block')
    r=region(-30,-28,65,65,25,26)
    add(5,['Y=65、X=-30〜-28、Z=25〜26の土を除去してください。ただしX=-30〜-28、Y=65、Z=25〜26は保護して残してください。'],
        clear(r,preserve_regions=[copy.deepcopy(r)]),refusal='protected_overlap')
    add(5,['X=26〜27、Y=65、Z=-30〜-29にオークの板材の床を敷いてください。材料不足なら着手せず中止してください。'],
        build('floor',region(26,27,65,65,-30,-29),'oak_planks'),refusal='missing_materials')
    return rows
