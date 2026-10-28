# Stage animation (how the clips are made)

The man-and-dog clips on the app's Run tab are rendered in Blender from two
3D models, then packed as animated WebP files in `assets/anim/`. Only those
rendered files ship with the app. You only need this folder to change the
animation.

## The models (not included - download them yourself)
Both are CC BY 4.0 (credit is in the main README):
- "Geoffrey Frisbee Throw - Disc Golf" by LasquetiSpice:
  https://sketchfab.com/3d-models/geoffrey-frisbee-throw-disc-golf-60b257e448df4cb0b55d4670026d4e6a
- "Stylized Low Poly German Shepherd" by DreamNoms:
  https://sketchfab.com/3d-models/stylized-low-poly-german-shepherd-18d8fbe184c5448283762893b6ea9752

Download each as **glTF Binary (.glb)** and save them as
`tools/animation/models/human.glb` and `tools/animation/models/dog.glb`.

## Render
```
pip install bpy          # Blender as a Python module (needs Python 3.11)
./render_all.sh          # needs ffmpeg; about 3 hours on a 2-core machine
```

## The clips
They join seamlessly through two shared moments:
- **hub**: the man holds the frisbee, the dog is ready to run
- **arrived**: the dog sits in front of him with the frisbee

| clip | from | to | what happens |
|---|---|---|---|
| `throw_s`, `throw_m`, `throw_l` | hub | arrived | throw (short, medium, long), chase, catch, run back, sit |
| `pet` | arrived | hub | he kneels, pets the dog, takes the frisbee, stands; the dog trots back |
| `finish` | hub | (end) | the dog sits by him, he kneels, drops the frisbee and keeps petting |

The app picks a random throw each round (never the same twice in a row) and
plays `finish` when a run ends. `assets/anim/clips.json` lists the files.
