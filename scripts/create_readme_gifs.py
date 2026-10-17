"""Render polished README replays from validated ALNS plans, without changing routes."""
import json
import sys
from pathlib import Path
import matplotlib
matplotlib.use('Agg')
import matplotlib.pyplot as plt
from matplotlib.patches import Rectangle, FancyBboxPatch
from PIL import Image

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
from demo.simulation import build_simulation_data
from src.generator import MAP_SCENARIOS, generate_scenario
from src.models import read_instance
from src.search import SearchConfig
from src.solver import solve
from src.validator import validate_solution

TITLES = {'single_block': 'Standard warehouse', 'double_block': 'Double-block warehouse',
          'mega_hub': 'Large warehouse', 'rush_hour': 'Rush hour',
          'abc_zonal': 'ABC zoning', 'kris_small': 'Kris Small benchmark'}
COLORS = ['#007f86', '#315ac7', '#c77315', '#9b4dba', '#c34365']


def position(picker, t, depot):
    for seg in picker['segments']:
        if seg['t_start'] <= t < seg['t_end']:
            f = (t-seg['t_start'])/(seg['t_end']-seg['t_start'])
            return (seg['x1']+f*(seg['x2']-seg['x1']),
                    seg['y1']+f*(seg['y2']-seg['y1']), seg)
    return depot['x'], depot['y'], None


def render(key, instance, output):
    result = solve(instance, 'ALNS', 42, SearchConfig(iterations=30, seconds=0))
    errors = validate_solution(instance, result)
    if errors:
        raise ValueError(errors)
    data = build_simulation_data(instance, result)
    kris = key == 'kris_small'
    time_factor = 1/1800 if kris else 1
    fig = plt.figure(figsize=(10, 6.4), dpi=100, facecolor='#edf2f7')
    fig.patches.append(Rectangle((0,.845),1,.155,transform=fig.transFigure,
                                 facecolor='#102338',edgecolor='none',zorder=-1))
    fig.text(.035,.947,'WAREHOUSE / LIVE REPLAY',color='#77d8cf',fontsize=10,weight='bold')
    fig.text(.035,.885,TITLES[key],color='white',fontsize=22,weight='bold')
    fig.text(.965,.94,'ALNS  /  SEED 42',ha='right',color='white',fontsize=10)
    fig.text(.965,.89,f'{len(instance.orders)} orders   |   {instance.operations.pickers} pickers',
             ha='right',color='#c8d7e9',fontsize=11)
    ax = fig.add_axes([.04,.14,.61,.65], facecolor='white')
    panel = fig.add_axes([.69,.14,.275,.65],facecolor='white')
    panel.set_xlim(0,1); panel.set_ylim(0,1); panel.axis('off')
    panel.add_patch(FancyBboxPatch((0,0),1,1,boxstyle='round,pad=0.015',
                                   facecolor='white',edgecolor='#dce4ee'))
    nodes = {n.id:n for n in instance.nodes}
    # Only synthetic layouts have explicit shelf geometry.
    if not kris:
        for block in data['shelf_blocks']:
            ax.add_patch(FancyBboxPatch((block['x'],block['y']),block['w'],block['h'],
                boxstyle='round,pad=0.03',facecolor='#e8eef5',edgecolor='#c7d2df',lw=.8))
    for edge in instance.edges:
        a,b=nodes[edge.source],nodes[edge.target]
        ax.plot([a.x,b.x],[a.y,b.y],color='#d5dfe9',lw=2,zorder=1)
    locations={p.location for p in instance.products}
    ax.scatter([nodes[n].x for n in locations],[nodes[n].y for n in locations],
               s=14,color='#8096ad',edgecolor='white',linewidth=.3,zorder=2)
    depot=data['depot']
    ax.scatter([depot['x']],[depot['y']],marker='s',s=145,color='#102338',edgecolor='#f2b84b',lw=2,zorder=9)
    ax.annotate('DEPOT',(depot['x'],depot['y']),xytext=(9,-14),textcoords='offset points',
                fontsize=8,color='#102338',weight='bold')
    ax.set_aspect('equal'); ax.margins(.12)
    ax.set_xlabel('x (source units)' if kris else 'x (m)',fontsize=8,color='#64748b')
    ax.set_ylabel('y (source units)' if kris else 'y (m)',fontsize=8,color='#64748b')
    ax.tick_params(labelsize=8,colors='#64748b',length=0,pad=5)
    for spine in ax.spines.values(): spine.set_color('#dce4ee')
    panel.text(.08,.94,'PICKER ACTIVITY',fontsize=10,color='#102338',weight='bold')
    artists=[]
    for i,picker in enumerate(data['pickers']):
        color=COLORS[i%len(COLORS)]; y=.84-i*.125
        marker,=ax.plot([],[],'o',ms=15,color=color,markeredgecolor='white',markeredgewidth=2,zorder=7)
        label=ax.text(0,0,str(picker['id']),ha='center',va='center',color='white',fontsize=7,weight='bold',zorder=8)
        trail,=ax.plot([],[],color=color,alpha=.75,lw=2.5,zorder=4,solid_capstyle='round')
        halo,=ax.plot([],[],'o',ms=25,color=color,alpha=.18,zorder=6)
        panel.text(.08,y,f"P{picker['id']}",color=color,fontsize=12,weight='bold')
        status=panel.text(.27,y,'',fontsize=10,color='#334155')
        panel.add_patch(Rectangle((.27,y-.045),.63,.011,facecolor='#e8eef5',edgecolor='none'))
        load=Rectangle((.27,y-.045),0,.011,facecolor=color,edgecolor='none');panel.add_patch(load)
        artists.append((marker,label,trail,halo,status,load))
    panel.text(.08,.13,'Orders completed',fontsize=10,color='#64748b')
    complete=panel.text(.08,.05,'',fontsize=20,color='#102338',weight='bold')
    clock=fig.text(.04,.07,'',fontsize=11,color='#102338',weight='bold')
    fig.text(.965,.07,'Validated plan  |  Compressed operational time',ha='right',fontsize=9,color='#64748b')
    fig.patches.append(Rectangle((.04,.035),.925,.009,transform=fig.transFigure,facecolor='#d4dee9',edgecolor='none'))
    progress=Rectangle((.04,.035),0,.009,transform=fig.transFigure,facecolor='#007f86',edgecolor='none');fig.patches.append(progress)
    frames=[]; total=data['makespan']
    for frame in range(160):
        t=total*frame/159
        for picker,art in zip(data['pickers'],artists):
            marker,label,trail,halo,status,load=art
            x,y,seg=position(picker,t,depot)
            marker.set_data([x],[y]);label.set_position((x,y))
            halo.set_data([x],[y]);halo.set_visible(seg is not None and seg['state']=='picking')
            state=seg['state'] if seg else ('done' if t>=max((s['t_end'] for s in picker['segments']),default=0) else 'idle')
            status.set_text({'traveling':'Moving','picking':'Picking items','setup':'Preparing','done':'Finished','idle':'Waiting'}.get(state,'At depot'))
            load.set_width(.63*min(1,seg['load']/data['capacity']) if seg else 0)
            # A short trail follows actual edges of the current batch only.
            points=[]
            if seg:
                for old in picker['segments']:
                    if old['batch_id']==seg['batch_id'] and old['state']=='traveling' and old['t_start']<=t and old['t_end']>=t-total*.09:
                        points.extend([(old['x1'],old['y1']), (old['x2'],old['y2'])] if old['t_end']<=t else [(old['x1'],old['y1']),(x,y)])
            trail.set_data([p[0] for p in points],[p[1] for p in points])
        completed=sum(o['completion']<=t+1e-8 for o in data['orders'])
        complete.set_text(f"{completed} / {len(instance.orders)}")
        clock.set_text(f'TIME  {t*time_factor:05.1f} / {total*time_factor:.1f} min')
        progress.set_width(.925*frame/159)
        fig.canvas.draw()
        im=Image.frombuffer('RGBA',fig.canvas.get_width_height(),fig.canvas.buffer_rgba(),'raw','RGBA',0,1).convert('RGB')
        if frame==70: im.save(output/f'{key}_preview.png')
        frames.append(im)
    # Use a shared palette to prevent frame-to-frame color flicker.
    palette=frames[70].quantize(colors=192)
    quantized=[im.quantize(palette=palette,dither=Image.Dither.NONE) for im in frames]
    path=output/f'{key}.gif'
    durations=[75]*len(frames);durations[0]=500;durations[-1]=1000
    quantized[0].save(path,save_all=True,append_images=quantized[1:],duration=durations,loop=0,optimize=True)
    plt.close(fig)
    print(f'{path.name}: {path.stat().st_size:,} bytes',flush=True)
    return {'file':path.name,'scenario':key,'instance':instance.name,'seed':42,'method':'ALNS',
            'iterations':30,'seconds':0,'validated':True,'coordinate_units':'source' if kris else 'metre',
            'display_time_factor':time_factor,'metrics':result['metrics']}


def main():
    output=ROOT/'assets'/'readme';output.mkdir(parents=True,exist_ok=True)
    cases=[(key,generate_scenario(key,seed=42)) for key in MAP_SCENARIOS]
    kris_path=ROOT/'data/processed/kris_small/instances_100_1.json'
    cases.append(('kris_small',read_instance(kris_path)))
    manifest=[render(key,instance,output) for key,instance in cases]
    (output/'manifest.json').write_text(json.dumps(manifest,indent=2),encoding='utf-8')


if __name__=='__main__':
    main()
