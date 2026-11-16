"""Small experiment: transparent ground AO and soft contact shading at arm joints."""
import bpy,math
from mathutils import Vector

def shade_arm_joints(plates,step,strength=.28,radius_px=2.0):
    for obj in plates:
        if obj.get('arm_kind')!='cut':continue
        pts=[obj.matrix_world@v.co for v in obj.data.vertices];c=sum(pts,Vector())/len(pts)
        axis=0 if abs(c.x)>abs(c.y)/math.sqrt(2) else 1;sign=1 if c[axis]>0 else -1
        scale=math.sqrt(2) if axis else 1;boundary=sign*step*.5*scale
        for i,source in enumerate(list(obj.data.materials)):
            mat=source.copy();mat.name='Probe_Seam_'+source.name;obj.data.materials[i]=mat
            nt=mat.node_tree;bsdf=next(n for n in nt.nodes if n.bl_idname=='ShaderNodeBsdfPrincipled');socket=bsdf.inputs['Base Color']
            geo=nt.nodes.new('ShaderNodeNewGeometry');sep=nt.nodes.new('ShaderNodeSeparateXYZ');nt.links.new(geo.outputs['Position'],sep.inputs[0])
            sub=nt.nodes.new('ShaderNodeMath');sub.operation='SUBTRACT';nt.links.new(sep.outputs[axis],sub.inputs[0]);sub.inputs[1].default_value=boundary
            absolute=nt.nodes.new('ShaderNodeMath');absolute.operation='ABSOLUTE';nt.links.new(sub.outputs[0],absolute.inputs[0])
            remap=nt.nodes.new('ShaderNodeMapRange');remap.interpolation_type='SMOOTHERSTEP';remap.clamp=True
            remap.inputs['From Min'].default_value=0;remap.inputs['From Max'].default_value=step/64*radius_px*scale
            remap.inputs['To Min'].default_value=1-strength;remap.inputs['To Max'].default_value=1
            nt.links.new(absolute.outputs[0],remap.inputs['Value'])
            mult=nt.nodes.new('ShaderNodeMixRGB');mult.blend_type='MULTIPLY';mult.inputs[0].default_value=1
            if socket.is_linked:nt.links.new(socket.links[0].from_socket,mult.inputs[1])
            else:mult.inputs[1].default_value=socket.default_value
            nt.links.new(remap.outputs['Result'],mult.inputs[2]);nt.links.new(mult.outputs[0],socket)

def render_ground_ao(ctx,placed,step,path):
    sc=ctx['sc'];saved={}
    for objs in placed.values():
        for o in objs:
            saved[o]=(o.hide_render,o.visible_camera,o.is_holdout,o.is_shadow_catcher)
            o.hide_render=o not in placed['plates'];o.visible_camera=False;o.is_holdout=False;o.is_shadow_catcher=False
    alpha=ctx['alpha'];oldalpha=alpha.hide_render;alpha.hide_render=True
    mesh=bpy.data.meshes.new('Probe_Ground_AO');r=step*3;z=ctx['sea']
    mesh.from_pydata([(-r,-r,z),(r,-r,z),(r,r,z),(-r,r,z)],[],[(0,1,2,3)])
    plane=bpy.data.objects.new('Probe_Ground_AO',mesh);sc.collection.objects.link(plane)
    mat=bpy.data.materials.new('Probe_Ground_Transparent_AO');mat.use_nodes=True;nt=mat.node_tree;nt.nodes.clear()
    ao=nt.nodes.new('ShaderNodeAmbientOcclusion');ao.samples=8;ao.inputs['Distance'].default_value=step/64*8
    inv=nt.nodes.new('ShaderNodeMath');inv.operation='SUBTRACT';inv.inputs[0].default_value=1;nt.links.new(ao.outputs['AO'],inv.inputs[1])
    strength=nt.nodes.new('ShaderNodeMath');strength.operation='MULTIPLY';strength.inputs[1].default_value=.5;nt.links.new(inv.outputs[0],strength.inputs[0])
    transparent=nt.nodes.new('ShaderNodeBsdfTransparent');black=nt.nodes.new('ShaderNodeEmission');black.inputs['Color'].default_value=(0,0,0,1)
    mix=nt.nodes.new('ShaderNodeMixShader');nt.links.new(strength.outputs[0],mix.inputs[0]);nt.links.new(transparent.outputs[0],mix.inputs[1]);nt.links.new(black.outputs[0],mix.inputs[2]);nt.links.new(mix.outputs[0],nt.nodes.new('ShaderNodeOutputMaterial').inputs['Surface']);mesh.materials.append(mat)
    keep=(sc.render.use_compositing,sc.view_settings.view_transform,sc.cycles.samples)
    sc.render.use_compositing=False;sc.view_settings.view_transform='Standard';sc.cycles.samples=32;sc.render.filepath=str(path)
    bpy.ops.render.render(write_still=True)
    sc.render.use_compositing,sc.view_settings.view_transform,sc.cycles.samples=keep
    alpha.hide_render=oldalpha
    for o,settings in saved.items():o.hide_render,o.visible_camera,o.is_holdout,o.is_shadow_catcher=settings
    bpy.data.objects.remove(plane,do_unlink=True);bpy.data.meshes.remove(mesh);bpy.data.materials.remove(mat)
