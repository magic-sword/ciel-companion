"""Compare the supplied v14c model render against the new material composite."""
import sys
sys.dont_write_bytecode=True
from build import *

def main():
    supplied=Image.open(GEN/'inputs/body-compare-v14c.png').convert('RGB')
    w=supplied.width//2;h=supplied.height
    bg=supplied.getpixel((0,0))
    current=Image.open(GEN/'proofs/v15-composite.png').convert('RGBA').crop((0,1200,2172,2896))
    current=flatten(current,bg).resize((w,h),Image.Resampling.LANCZOS)
    out=Image.new('RGB',(w*3,h+44),'#e8ebf1');d=ImageDraw.Draw(out)
    for i,(label,im) in enumerate([('Approved original (supplied)',supplied.crop((0,0,w,h))),('v14c model render (supplied)',supplied.crop((w,0,w*2,h))),('v15 material composite',current)]):
        d.text((i*w+12,10),label,font=FONT,fill='#202738');out.paste(im,(i*w,44))
    out.save(GEN/'proofs/comparison-supplied-model-body.png')
    print('Wrote comparison using supplied v14c model render.')

if __name__=='__main__':main()
