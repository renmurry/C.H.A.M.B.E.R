"""Export MobileSAM (Apache-2.0, github.com/ChaoningZhang/MobileSAM) to two ONNX
files the app runs with onnxruntime, so the app itself needs no PyTorch.

    pip install torch timm onnx
    pip install git+https://github.com/ChaoningZhang/MobileSAM.git
    python tools/models/export_mobilesam.py path/to/mobile_sam.pt assets/models

encoder: image (1,3,1024,1024) float32, already normalised -> embeddings (1,256,64,64)
decoder: SAM prompt decoder, all 4 masks (index 0 = single-mask head, 1-3 = the
         three multimask choices) at the size given in orig_im_size.
"""
import sys, warnings
from pathlib import Path
import torch
from mobile_sam import sam_model_registry
from mobile_sam.utils.onnx import SamOnnxModel

ckpt, out = sys.argv[1], Path(sys.argv[2]); out.mkdir(parents=True, exist_ok=True)
sam = sam_model_registry["vit_t"](checkpoint=ckpt).eval()
warnings.filterwarnings("ignore")

with torch.no_grad():
    torch.onnx.export(sam.image_encoder, torch.randn(1, 3, 1024, 1024), str(out / "sam_encoder.onnx"),
                      input_names=["image"], output_names=["embeddings"], opset_version=17,
                      do_constant_folding=True, dynamo=False)

    dec = SamOnnxModel(sam, return_single_mask=False).eval()
    emb = torch.randn(1, 256, 64, 64)
    dummy = {"image_embeddings": emb,
             "point_coords": torch.randint(0, 1024, (1, 5, 2), dtype=torch.float),
             "point_labels": torch.randint(0, 4, (1, 5), dtype=torch.float),
             "mask_input": torch.randn(1, 1, 256, 256),
             "has_mask_input": torch.tensor([1], dtype=torch.float),
             "orig_im_size": torch.tensor([1500, 2250], dtype=torch.float)}
    torch.onnx.export(dec, tuple(dummy.values()), str(out / "sam_decoder.onnx"),
                      input_names=list(dummy), output_names=["masks", "iou_predictions", "low_res_masks"],
                      dynamic_axes={"point_coords": {1: "num_points"}, "point_labels": {1: "num_points"}},
                      opset_version=17, do_constant_folding=True, dynamo=False)
print("written:", *sorted(p.name for p in out.glob("*.onnx")))
