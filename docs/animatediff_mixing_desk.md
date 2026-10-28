# AnimateDiff-LCM on the APC40: the mixing desk

Machine Delusions' AnimateDiff-LCM workflows (Patreon, parts 1 and 2) are
render engines, not instruments: a clip takes minutes. What the APC40 adds is
a mixing desk in front of them. Set the strengths by feel, hit a pad to
queue, compare clips. ControlFreak does the mapping with no code.

## Getting the graphs

The originals are paid, so this repo ships only the converter:

```bash
python scripts/convert_animatediff_lcm.py "AnimateDiff-LCM-Experiments.json" "AnimateDiff-LCM-Experiments - Part 2.json"
```

This writes `workflows/animatediff_lcm_part1.json` and `_part2.json` (gitignored)
with the Fill-Nodes upscale, selector and RIFE swapped for core nodes, the SAM3
preview pair removed, and the motion module pointed at the Hugging Face
`AnimateLCM_sd15_t2v.ckpt`. Drop them into your ComfyUI workflows folder.

## Packs and models

Packs: AnimateDiff-Evolved, KJNodes, VideoHelperSuite, IPAdapter Plus,
Advanced ControlNet, controlnet_aux, RMBG (part 2). Models, under the models
root:

| Folder | File | Source |
|---|---|---|
| checkpoints/SD1.5/LCM | photon-LCM.safetensors | moonshotmillion/Photon_LCM_1.5 (`photonLCM_v10.safetensors`, renamed) |
| animatediff_models | AnimateLCM_sd15_t2v.ckpt | wangfuyun/AnimateLCM |
| ipadapter | ip-adapter-plus_sd15.bin | h94/IP-Adapter |
| clip_vision/SD1.5 | model.safetensors | h94/IP-Adapter image_encoder |
| upscale_models | 4x-UltraSharp.pth | lokCX/4x-Ultrasharp |
| controlnet/1.5 | control_v11p_sd15_lineart.pth, control_v11f1p_sd15_depth.pth, control_v11f1e_sd15_tile.pth | lllyasviel/ControlNet-v1-1 |

## The desk: what goes on which control

ControlFreak: right-click a widget, choose *Map to controller*, move the
control. Mappings save inside the workflow file. Suggested layout, part 1:

| APC40 control | Widget | Why |
|---|---|---|
| device knobs 1-3 | the three `IPAdapterBatch` **weight** (top, middle, bottom) | how hard each reference image holds its band |
| device knob 4 | `AnimateDiff Loader` **motion_scale** | 0.8 calm, 1.3 wild |
| device knobs 5-7 | the three `KSampler` **denoise** (base 1.0, then 0.6, 0.4) | the second and third are the upscale passes; lower keeps the base clip |
| device knob 8 | base `KSampler` **steps** (6 to 12) | LCM only needs a few |
| track knob 1 | `EmptyLatentImage` **batch_size** (16 to 48) | clip length in frames |
| master fader | first `ImageScaleBy` **scale_by** (0.3 to 0.5) | output size, and render time |
| pad row 1 | **Queue Prompt** | the render button |
| pad row 2 | **Interrupt** | the oops button |

Part 2 adds the three `Apply Advanced ControlNet` nodes. Their **strength**
(the video's sweet spot is 0.2 to 0.35) and **end_percent** are the knobs that
matter; put them on track knobs 2 to 7.

The prompt stays on the keyboard. A knob cannot type.

## Why not FaderFace's own nodes here

`APC40 Knob` plus the queue-on-knob extension re-render on every tick, which
is right for a quarter-second face and wrong for a three-minute clip. For a
batch render you want knobs that only set values and one deliberate button
that queues. That is exactly ControlFreak's shape, so it is the right tool
for this graph.

## Subgraph fold

Once the plain copies run, select the whole render engine in the canvas and
convert it to a subgraph, then promote the widgets above onto the parent
node. One tidy node, twelve handles, nothing else on the canvas. The frontend
owns the subgraph format, so do the fold there, not in a text editor.
