/** OpenAtlas real-time scene helpers. Copy into editable source when useful.
 * Coordinates and bounds must use one shared source coordinate system.
 * Rendering stays in the application's requestAnimationFrame loop.
 */
export function timeline(scroll, anchors) {
  if (anchors.length < 2 || anchors.some((x,i)=>!Number.isFinite(x)||(i && x<=anchors[i-1]))) throw new Error('Timeline anchors must increase');
  const position = Math.min(anchors.at(-1), Math.max(anchors[0], scroll));
  let from = 0;
  while (from < anchors.length-2 && position >= anchors[from+1]) from++;
  const t = (position-anchors[from])/(anchors[from+1]-anchors[from]);
  return {from, to:from+1, t:t*t*(3-2*t)};
}

export function groupsAtScope(nodes, scope, hidden = new Set()) {
  const root = nodes[scope];
  if (!root) throw new Error('Unknown scope');
  const ids = root.children.length ? root.children : [scope];
  const seen = new Set();
  const groups = ids.map(id=>{
    const node = nodes[id];
    if (!node) throw new Error('Missing child');
    const members = node.members.filter(key=>!hidden.has(key));
    for (const key of members) {
      if (seen.has(key)) throw new Error('A mesh belongs to multiple exploded groups');
      seen.add(key);
    }
    return {id, name:node.name, members};
  }).filter(group=>group.members.length);
  const eligible = root.members.filter(key=>!hidden.has(key));
  if (seen.size !== eligible.length || eligible.some(key=>!seen.has(key))) throw new Error('Child groups do not cover their parent');
  return groups;
}

export function separatedLayout(groups, bounds, {page=0,pageSize=8,columns=3,extent=1.6,gap=.65}={}) {
  if (![page,pageSize,columns].every(Number.isInteger) || page<0 || pageSize<1 || columns<1 || extent<=0 || gap<0) throw new Error('Invalid layout');
  const pages = Math.max(1, Math.ceil(groups.length/pageSize));
  page = Math.min(page, pages-1);
  const visible = groups.slice(page*pageSize,(page+1)*pageSize);
  const cols = Math.min(columns,visible.length), rows = Math.ceil(visible.length/columns);
  const items = visible.map((group,index)=>{
    const lo=[Infinity,Infinity,Infinity],hi=[-Infinity,-Infinity,-Infinity];
    for(const id of group.members) {
      const b=bounds[id];
      if(!b || b.min.some((v,i)=>!Number.isFinite(v)||!Number.isFinite(b.max[i])||v>b.max[i])) throw new Error('Invalid source bounds');
      for(let i=0;i<3;i++){lo[i]=Math.min(lo[i],b.min[i]);hi[i]=Math.max(hi[i],b.max[i]);}
    }
    const center=lo.map((v,i)=>(v+hi[i])/2);
    const scale=extent/Math.max(...hi.map((v,i)=>v-lo[i]),1e-8);
    const destination=[(index%columns-(cols-1)/2)*(extent+gap),((rows-1)/2-Math.floor(index/columns))*(extent+gap),0];
    return {...group,scale,translation:destination.map((v,i)=>v-center[i]*scale)};
  });
  return {page,pages,items};
}

export function meshTargets(allIds, layout, amount, hidden=new Set()) {
  const t=Math.max(0,Math.min(1,amount)), byId=new Map();
  for(const group of layout.items) for(const id of group.members) byId.set(id,group);
  return allIds.map(id=>{
    const g=byId.get(id);
    return {id,scale:g?1+(g.scale-1)*t:1,position:g?g.translation.map(v=>v*t):[0,0,0],opacity:hidden.has(id)?0:g?1:1-t};
  });
}
