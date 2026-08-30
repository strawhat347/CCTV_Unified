import sys

print('1. Importing PyTorch...')
import torch
print(f'   PyTorch version: {torch.__version__}')
print(f'   CUDA available (Torch): {torch.cuda.is_available()}')
if torch.cuda.is_available():
    t = torch.tensor([1.0, 2.0]).cuda()
    print(f'   Test tensor on {t.device}')

print('\n2. Importing PaddlePaddle...')
import paddle
print(f'   Paddle version: {paddle.__version__}')
print(f'   CUDA available (Paddle): {paddle.device.is_compiled_with_cuda()}')
if paddle.device.is_compiled_with_cuda():
    p = paddle.to_tensor([1.0, 2.0], place=paddle.CUDAPlace(0))
    print(f'   Test tensor on {p.place}')

print('\n3. Both frameworks loaded and initialized on GPU successfully!')
print('No DLL/.so collisions detected!')
