import os
from functools import wraps

import utils
from mlperf_logging import mllog


class SSDLogger():
    def __init__(self, rank, filename=None, default_stack_offset=2):
        self.rank = rank
        self.mllogger = mllog.get_mllogger()
        mllog.config(default_stack_offset=default_stack_offset,
                     filename=(filename or os.getenv("COMPLIANCE_FILE") or "mlperf_compliance.log"),
                     root_dir=os.path.normpath(os.path.dirname(os.path.realpath(__file__))))

    def event(self, sync=False, ranks=None, *args, **kwargs):
        ranks = self.rank if ranks is None else ranks
        ranks = [ranks] if not isinstance(ranks, list) else ranks
        if sync:
            utils.barrier()
        if self.rank in ranks:
            self.mllogger.event(kwargs)

    def start(self, sync=False, ranks=None, *args, **kwargs):
        ranks = self.rank if ranks is None else ranks
        ranks = [ranks] if not isinstance(ranks, list) else ranks
        if sync:
            utils.barrier()
        if self.rank in ranks:
            self.mllogger.start(kwargs)

    def end(self, sync=False, ranks=None, *args, **kwargs):
        ranks = self.rank if ranks is None else ranks
        ranks = [ranks] if not isinstance(ranks, list) else ranks
        if sync:
            utils.barrier()
        if self.rank in ranks:
            self.mllogger.end(kwargs)
