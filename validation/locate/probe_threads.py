"""Diagnostic: torch's thread count before and during Lightning training (one tiny fit).
Usage: python probe_threads.py <original|lightning2>"""

import os
import sys

import pytorch_lightning as pl
import torch
from torch.utils.data import DataLoader, TensorDataset


class Tiny(pl.LightningModule):
    def __init__(self):
        super().__init__()
        self.layer = torch.nn.Linear(2, 1)
        self.seen = None

    def training_step(self, batch, batch_idx):
        self.seen = torch.get_num_threads()
        return self.layer(batch[0]).sum()

    def configure_optimizers(self):
        return torch.optim.SGD(self.parameters(), lr=0.1)


before = torch.get_num_threads()
model = Tiny()
extra = {"accelerator": "cpu", "devices": 1} if sys.argv[1] == "lightning2" else {}
trainer = pl.Trainer(max_epochs=1, logger=False, enable_checkpointing=False, enable_progress_bar=False,
                     enable_model_summary=False, **extra)
trainer.fit(model, DataLoader(TensorDataset(torch.ones(4, 2)), batch_size=2))
print(f"lightning {pl.__version__}: threads before {before}, during training {model.seen}, "
      f"after {torch.get_num_threads()}; OMP_NUM_THREADS={os.environ.get('OMP_NUM_THREADS')}; cpus={os.cpu_count()}")
