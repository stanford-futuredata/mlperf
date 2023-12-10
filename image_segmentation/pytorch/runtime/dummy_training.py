from tqdm import tqdm

import torch
from torch.optim import Adam, SGD
from torch.cuda.amp import autocast, GradScaler

from runtime.distributed_utils import get_rank, reduce_tensor, get_world_size
from runtime.inference import evaluate
from runtime.logging import mllog_event, mllog_start, mllog_end, CONSTANTS


def get_optimizer(params, flags):
    if flags.optimizer == "adam":
        optim = Adam(params, lr=flags.learning_rate, weight_decay=flags.weight_decay)
    elif flags.optimizer == "sgd":
        optim = SGD(params, lr=flags.learning_rate, momentum=flags.momentum, nesterov=True,
                    weight_decay=flags.weight_decay)
    elif flags.optimizer == "lamb":
        import apex
        optim = apex.optimizers.FusedLAMB(params, lr=flags.learning_rate, betas=flags.lamb_betas,
                                          weight_decay=flags.weight_decay)
    else:
        raise ValueError("Optimizer {} unknown.".format(flags.optimizer))
    return optim


def lr_warmup(optimizer, init_lr, lr, current_samples, warmup_samples):
    scale = current_samples / warmup_samples
    for param_group in optimizer.param_groups:
        param_group['lr'] = init_lr + (lr - init_lr) * scale


def train(flags, model, train_loader, val_loader, loss_fn, score_fn, device, callbacks,
          is_distributed, samples_per_epoch):
    rank = get_rank()
    world_size = get_world_size()
    torch.backends.cudnn.benchmark = flags.cudnn_benchmark
    torch.backends.cudnn.deterministic = flags.cudnn_deterministic

    optimizer = get_optimizer(model.parameters(), flags)
    if flags.lr_decay_samples:
        scheduler = torch.optim.lr_scheduler.MultiStepLR(optimizer,
                                                         milestones=flags.lr_decay_samples,
                                                         gamma=flags.lr_decay_factor)
    scaler = GradScaler()

    model.to(device)
    loss_fn.to(device)
    if is_distributed:
        model = torch.nn.parallel.DistributedDataParallel(model,
                                                          device_ids=[flags.local_rank],
                                                          output_device=flags.local_rank)

    is_successful = False
    diverged = False
    total_samples = 0
    iteration = 0
    next_eval_at = flags.start_eval_at
    model.train()
    train_loader = iter(train_loader)
    for callback in callbacks:
        callback.on_fit_start()

    counts = {}
    while not diverged and not is_successful:
        mllog_start(key=CONSTANTS.BLOCK_START, sync=False,
                    metadata={CONSTANTS.FIRST_EPOCH_NUM: total_samples,
                              CONSTANTS.EPOCH_COUNT: next_eval_at})

        while total_samples < next_eval_at:
            if total_samples <= flags.lr_warmup_samples and flags.lr_warmup_samples > 0:
                lr_warmup(optimizer, flags.init_learning_rate, flags.learning_rate, total_samples, flags.lr_warmup_samples)

            optimizer.zero_grad()
            # for iteration, batch in enumerate(tqdm(train_loader, disable=(rank != 0) or not flags.verbose)):

            batch = next(train_loader)
            total_samples = flags.batch_size * world_size

            image, label = batch
            # image, label = image.to(device), label.to(device)

            iteration += 1
            print(total_samples)
            for b in batch:
                print(*b)


        # Evaluation
        mllog_start(key=CONSTANTS.EVAL_START, value=total_samples,
                    metadata={CONSTANTS.EPOCH_NUM: total_samples}, sync=False)



        mllog_end(key=CONSTANTS.EVAL_STOP, metadata={CONSTANTS.EPOCH_NUM: total_samples}, sync=False)

        model.train()

        mllog_end(key=CONSTANTS.BLOCK_STOP, sync=False,
                  metadata={CONSTANTS.FIRST_EPOCH_NUM: total_samples,
                            CONSTANTS.EPOCH_COUNT: next_eval_at})
        next_eval_at += flags.evaluate_every


    mllog_end(key=CONSTANTS.RUN_STOP, sync=True,
              metadata={CONSTANTS.STATUS: CONSTANTS.SUCCESS if is_successful else CONSTANTS.ABORTED,
                        CONSTANTS.EPOCH_COUNT: total_samples})
    for callback in callbacks:
        callback.on_fit_end()
