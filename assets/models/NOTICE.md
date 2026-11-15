# Model files

`sam_encoder.onnx` and `sam_decoder.onnx` are MobileSAM ("Faster Segment
Anything: Towards Lightweight SAM for Mobile Applications", Zhang et al., 2023),
converted to ONNX so the app can run them with onnxruntime, offline, on the CPU.

- Source: https://github.com/ChaoningZhang/MobileSAM
- Licence: Apache License 2.0 (copy in `LICENSE-MobileSAM.txt`)
- Changes made: the published `mobile_sam.pt` weights were exported to two ONNX
  files (image encoder; prompt encoder + mask decoder) with
  `tools/models/export_mobilesam.py`. The weights themselves are unchanged.
