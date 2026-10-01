"""Read-only calibration of real existing Valley c01, before selecting notch parameters."""
import json
from pathlib import Path
import numpy as np
from PIL import Image, ImageDraw
from copox.adapters.alth_character_audit import load_scene, load_config, crop_norm, person_mask, region_mask, registration_from_baseline, raster_silhouette
from copox.adapters.finger_gap_plan import _pixel_to_norm
from copox.adapters.finger_valley_probe import _valleys

def diagnose(parent, reference, config, output):
    cfg=load_config(config); scale=float(cfg.get("mesh_to_mm",1000))
    scene,mesh=load_scene(parent,scale)
    rows=[]
    for node in scene.graph.nodes_geometry:
        matrix,name=scene.graph.get(node); geom=scene.geometry[name]
        if hasattr(geom,"vertices"):
            world=(matrix@np.column_stack([geom.vertices,np.ones(len(geom.vertices))]).T).T[:,:3]
            rows.append((len(world),world))
    world=max(rows,key=lambda row:row[0])[1]
    lo,hi=world.min(0),world.max(0); span=hi-lo; norm=(world-lo)/span
    front=crop_norm(np.array(Image.open(reference).convert("RGB")),cfg["views"]["front"])
    mask=person_mask(front); registration=registration_from_baseline(mesh,"front",mask,cfg)
    mod=raster_silhouette(mesh,"front",mask.shape,registration,cfg)
    roi=region_mask(mask,cfg["regions_by_view"]["hands"][0]["box"])
    ref=mask&roi
    valleys=_valleys(ref,roi,"left")
    result={"registration":registration,"canonical_bounds":[lo.tolist(),hi.tolist()],"valleys":[]}
    mb=np.array(cfg["morph_regions"]["fingers"]["boxes"][0])
    selected=norm[np.all((norm>=mb[:3])&(norm<=mb[3:]),1)]
    for valley in valleys:
        x0,y0,x1,y1=valley["bbox_px"]
        nx0,zhi=_pixel_to_norm(x0,y0,registration,lo,span,scale)
        nx1,zlo=_pixel_to_norm(x1+1,y1+1,registration,lo,span,scale)
        band=selected[(selected[:,2]>=zlo)&(selected[:,2]<=zhi)]
        result["valleys"].append({"source":valley,"mapped_x":[nx0,nx1],"mapped_z":[zlo,zhi],
           "selected_vertices":len(band),"distal_x":float(band[:,0].min()) if len(band) else None,
           "material_xmax":float(band[:,0].max()) if len(band) else None,
           "gap_depth_normalized":float(valley["width_px"]/registration["scale"]/scale/span[0])})
    Path(output).mkdir(parents=True,exist_ok=True)
    Path(output,"diagnostic.json").write_text(json.dumps(result,indent=2))
    rgb=np.full((*mask.shape,3),255,dtype=np.uint8)
    rgb[mask]=[40,120,210]; rgb[mod&~mask]=[240,80,60]; rgb[mask&mod]=[110,110,110]
    image=Image.fromarray(rgb); draw=ImageDraw.Draw(image)
    for row in result["valleys"]: draw.rectangle(row["source"]["bbox_px"],outline="black",width=2)
    yy,xx=np.where(roi)
    image.crop((max(0,int(xx.min())-10),max(0,int(yy.min())-10),min(image.width,int(xx.max())+11),min(image.height,int(yy.max())+11))).resize((640,640)).save(Path(output,"registration.png"))
    print("COPOX_CALIBRATION:"+json.dumps(result))
    import base64
    print("COPOX_REVIEW_IMAGE:"+base64.b64encode(Path(output,"registration.png").read_bytes()).decode())
    return result

if __name__=="__main__":
    diagnose(".copox/source/working_parent/model.glb","refs/personajes/joven-rubio-4-vistas.jpg",
        "copox/reference_configs/joven_rubio_alpha.json",".copox/connected-diagnostic")
