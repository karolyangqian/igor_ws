"""Generate a simple editable draw.io chip diagram and matching SVG/PNG preview."""
from pathlib import Path
import html
import sys
import xml.etree.ElementTree as ET

ROOT = Path(__file__).resolve().parents[1]
OUT = ROOT / 'docs/assets'
OUT.mkdir(parents=True, exist_ok=True)
mxfile = ET.Element('mxfile', host='app.diagrams.net', type='device')
diagram = ET.SubElement(mxfile, 'diagram', id='igor-core', name='IGOR Core')
model = ET.SubElement(diagram, 'mxGraphModel', dx='1600', dy='1000', grid='1',
                      gridSize='10', guides='1', tooltips='1', connect='1',
                      arrows='1', fold='1', page='1', pageScale='1',
                      pageWidth='1600', pageHeight='1000', math='0', shadow='0')
root = ET.SubElement(model, 'root')
ET.SubElement(root, 'mxCell', id='0')
ET.SubElement(root, 'mxCell', id='1', parent='0')
svg = ['<svg xmlns="http://www.w3.org/2000/svg" width="1600" height="1000" viewBox="0 0 1600 1000">',
       '<defs><marker id="arrow" markerWidth="10" markerHeight="10" refX="9" refY="5" orient="auto" markerUnits="userSpaceOnUse"><path d="M0,0 L10,5 L0,10 Z" fill="#334155"/></marker></defs>',
       '<rect width="1600" height="1000" fill="white"/>']
boxes = {}


def text_svg(x, y, label, size, color='#0f172a', bold=False):
    lines = label.split('\n')
    start = y - (len(lines)-1)*size*.66
    for i, line in enumerate(lines):
        svg.append(f'<text x="{x}" y="{start+i*size*1.32}" text-anchor="middle" dominant-baseline="middle" font-family="Arial, sans-serif" font-size="{size}" fill="{color}" font-weight="{700 if bold else 400}">{html.escape(line)}</text>')


def box(key, x, y, w, h, label='', fill='#ffffff', stroke='#334155', size=18,
        bold=False, text='#0f172a', radius=16, width=2):
    boxes[key] = (x,y,w,h)
    style = (f'rounded={int(radius>0)};whiteSpace=wrap;html=0;arcSize=12;'
             f'fillColor={fill};strokeColor={stroke};strokeWidth={width};'
             f'fontFamily=Arial;fontSize={size};fontColor={text};fontStyle={int(bold)};'
             'align=center;verticalAlign=middle;spacing=8;')
    cell = ET.SubElement(root, 'mxCell', id=key, value=label, style=style, vertex='1', parent='1')
    ET.SubElement(cell, 'mxGeometry', x=str(x), y=str(y), width=str(w), height=str(h), **{'as':'geometry'})
    svg.append(f'<rect x="{x}" y="{y}" width="{w}" height="{h}" rx="{radius}" fill="{fill}" stroke="{stroke}" stroke-width="{width}"/>')
    if label:
        text_svg(x+w/2,y+h/2,label,size,text,bold)


def label(key,x,y,w,h,value,size=18,color='#475569',bold=False):
    cell=ET.SubElement(root,'mxCell',id=key,value=value,vertex='1',parent='1',
        style=f'text;html=0;strokeColor=none;fillColor=none;align=center;verticalAlign=middle;fontFamily=Arial;fontSize={size};fontColor={color};fontStyle={int(bold)};whiteSpace=wrap;')
    ET.SubElement(cell,'mxGeometry',x=str(x),y=str(y),width=str(w),height=str(h),**{'as':'geometry'})
    text_svg(x+w/2,y+h/2,value,size,color,bold)


def edge(key,source,target,points,exit_xy,entry_xy,dashed=False):
    style = (f'edgeStyle=orthogonalEdgeStyle;rounded=0;html=0;endArrow=block;endFill=1;strokeColor=#334155;strokeWidth=2.5;'
             f'exitX={exit_xy[0]};exitY={exit_xy[1]};exitDx=0;exitDy=0;'
             f'entryX={entry_xy[0]};entryY={entry_xy[1]};entryDx=0;entryDy=0;'
             f'dashed={int(dashed)};')
    cell=ET.SubElement(root,'mxCell',id=key,edge='1',parent='1',source=source,target=target,style=style)
    geom=ET.SubElement(cell,'mxGeometry',relative='1',**{'as':'geometry'})
    if len(points)>2:
        arr=ET.SubElement(geom,'Array',**{'as':'points'})
        for x,y in points[1:-1]:
            ET.SubElement(arr,'mxPoint',x=str(x),y=str(y))
    path='M'+' L'.join(f'{x},{y}' for x,y in points)
    dash=' stroke-dasharray="7 5"' if dashed else ''
    svg.append(f'<path d="{path}" fill="none" stroke="#334155" stroke-width="2.5" marker-end="url(#arrow)"{dash}/>')


label('title',200,30,1200,55,'IGOR CORE',34,'#0f172a',True)
label('subtitle',200,87,1200,35,'Neural inference · 74 → 128 → 64 → 3 · Parallel8',20)

# Decorative package pins, explicitly separate from functional ports.
for side,x in [('left',240),('right',1340)]:
    for i,y in enumerate(range(265,826,40)):
        box(f'pin-{side}-{i}',x,y,20,12,fill='#94a3b8',stroke='#64748b',radius=2,width=1)
box('chip',260,150,1080,710,fill='#f8fafc',stroke='#0f172a',radius=28,width=4)
box('chip-header',295,175,1010,65,'IGOR  |  FPGA NEURAL CORE',fill='#0f172a',stroke='#0f172a',size=25,bold=True,text='#ffffff')
box('memory',520,290,560,100,'MEMORY\nweights + bias\n8 bank ROM · M10K · 64 KiB',fill='#ede9fe',stroke='#7c3aed',size=20,bold=True)
box('input',15,470,200,110,'INPUT\n74 observasi\n16-bit fixed-point',fill='#eff6ff',stroke='#2563eb',size=19,bold=True)
box('storage',325,470,210,110,'DATA STORAGE\nInput + hidden\nactivation',fill='#e0f2fe',stroke='#0284c7',size=18,bold=True)
box('multiply',590,470,180,110,'8× MULTIPLIER\ninput × weights',fill='#dbeafe',stroke='#2563eb',size=18,bold=True)
box('accumulator',825,470,180,110,'8× ACCUMULATOR\nbias + Σ products\n40-bit signed',fill='#cffafe',stroke='#0891b2',size=16,bold=True)
box('activation',1060,470,210,110,'ACTIVATION\nReLU / clamp\n16-bit',fill='#dcfce7',stroke='#16a34a',size=19,bold=True)
box('output',1395,470,190,110,'OUTPUT\n3 residual AI\n16-bit fixed-point',fill='#f0fdf4',stroke='#16a34a',size=18,bold=True)
box('control',600,745,400,80,'CONTROL / FSM\nMengatur memory, MAC, dan activation',fill='#e2e8f0',stroke='#64748b',size=17,bold=True)
box('control-input',15,745,200,80,'CONTROL INPUT\nclock · reset\nstart · abort',fill='#f8fafc',stroke='#94a3b8',size=16)
box('status',1395,745,190,80,'STATUS\nbusy · done · fault\nerror_code',fill='#f8fafc',stroke='#94a3b8',size=16)

edge('input-data','input','storage',[(215,525),(325,525)],(1,.5),(0,.5))
edge('operand','storage','multiply',[(535,525),(590,525)],(1,.5),(0,.5))
edge('weights','memory','multiply',[(680,390),(680,470)],(160/560,1),(.5,0))
edge('bias','memory','accumulator',[(915,390),(915,470)],(395/560,1),(.5,0))
edge('products','multiply','accumulator',[(770,525),(825,525)],(1,.5),(0,.5))
edge('sum','accumulator','activation',[(1005,525),(1060,525)],(1,.5),(0,.5))
edge('result','activation','output',[(1270,525),(1395,525)],(1,.5),(0,.5))
edge('hidden-feedback','activation','storage',[(1165,580),(1165,650),(430,650),(430,580)],(.5,1),(.5,1))
edge('control-in','control-input','control',[(215,785),(600,785)],(1,.5),(0,.5),True)
edge('control-out','control','status',[(1000,785),(1395,785)],(1,.5),(0,.5),True)
label('weights-label',690,410,110,30,'weights',17,'#6d28d9',True)
label('bias-label',925,410,80,30,'bias',17,'#6d28d9',True)
label('feedback-label',485,658,650,36,'Hidden activation → input untuk layer berikutnya',17)
label('mac-label',590,590,415,28,'MAC = multiplier + accumulator',15)
label('timing',250,895,1100,45,'6.916 siklus  ·  50 MHz  ·  138,32 µs  (<160 µs)',23,'#0f172a',True)
label('scope',250,950,1100,26,'Diagram fungsi core RTL · Pins ilustratif · Interface UART berada di wrapper',15)

ET.indent(mxfile,space='  ')
(OUT/'igor_core_simple.drawio').write_bytes(ET.tostring(mxfile,encoding='utf-8',xml_declaration=True))
svg.append('</svg>')
(OUT/'igor_core_simple.svg').write_text('\n'.join(svg),encoding='utf-8')
sys.path.insert(0,str(ROOT/'.runtime/diagram_renderer'))
import resvg_py
(OUT/'igor_core_simple.png').write_bytes(resvg_py.svg_to_bytes(svg_string='\n'.join(svg)))
print('Generated editable draw.io + SVG + PNG:',OUT/'igor_core_simple.drawio')
