# locate_lightning2: changes from LOCATE-model 0.0.3

Starting point: the two files of LOCATE-model 0.0.3 (PyPI, identical to
github.com/oshritshtossel/LOCATE), copied unchanged. Every change is marked
`[lightning2]` in the code. **The model's logic is unchanged**: the network, the
least-squares transformer with its low-rank SVD, the loss, the optimizers and their
settings, early stopping and the default hyperparameters are all the authors'.

## Why

The original needs Lightning 1.x, which needs Python ≤ 3.10. It trains two
optimizers (the representation network, and an unused discriminator) with Lightning's
*automatic* optimization. Lightning 2 removed automatic optimization with more than one
optimizer: it raises "Training with multiple optimizers is only supported with manual
optimization".

## The changes

`LOCATE_model.py`
1. `self.automatic_optimization = False` in `__init__`.
2. `training_step(self, train_batch, batch_idx)` (no `optimizer_idx`) performs, by hand,
   what Lightning 1.8.3 did automatically for each batch
   (pytorch_lightning/loops/optimization/optimizer_loop.py): for each optimizer in
   order, toggle it, run the original step for that optimizer index (a forward pass in
   training mode, which recomputes `self.X`), and only for optimizer 0, which returns a
   loss: zero the gradients, back-propagate, step; then untoggle. Optimizer 1 returned no
   loss and was never stepped, but its forward pass still ran (it consumes random
   numbers and recomputes `self.X`), so it still runs here.
3. `backward(self, loss, *args, **kwargs)`: Lightning 2 no longer passes the optimizer
   and its index. It still calls `loss.backward(retain_graph=True)`.

`LOCATE_functions.py`
4. `CSVLogger` instead of `TensorBoardLogger` (which in Lightning 2 needs the separate
   `tensorboard` package). Logging records the losses only; it does not affect training.
5. `pl.Trainer(..., accelerator="cpu", devices=1)`: Lightning 1.8 trained on the CPU
   unless told otherwise; Lightning 2 would pick a GPU when present.
6. `from .LOCATE_model import GeneralModel` instead of `from LOCATE import LOCATE_Model`
   (this package's name).

`__init__.py`: the same three names as the original (`LOCATE_Model`, `LOCATE_training`,
`LOCATE_predict`), plus `__version__` and `BASED_ON`.

## Validation

See `validation/locate/` in the microplatform repository: PROTOCOL.md (fixed before
running) and RESULTS.md.

## Licence

MIT, as the original; see LICENSE.txt (copied unchanged from LOCATE-model 0.0.3; its
copyright line is the packaging template's).
