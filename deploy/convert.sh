#!/bin/sh
# Execute INSIDE an official Pulsar2 container with this folder mounted at /data.
set -eu
pulsar2 build --target_hardware AX620E --input ./export.onnx --output_dir ./build_npu --config ./config/npu.json
pulsar2 build --target_hardware AX620E --input ./export.onnx --output_dir ./build_vnpu --config ./config/vnpu.json
mkdir -p out
cp build_npu/compiled.axmodel out/milu_npu.axmodel
cp build_vnpu/compiled.axmodel out/milu_vnpu.axmodel
cp milu.mud out/milu.mud
echo 'Copy all three files from out/ to the application models/ directory.'
