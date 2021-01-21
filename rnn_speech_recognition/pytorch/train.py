# Copyright (c) 2019-2020, NVIDIA CORPORATION. All rights reserved.
#
# Licensed under the Apache License, Version 2.0 (the "License");
# you may not use this file except in compliance with the License.
# You may obtain a copy of the License at
#
#           http://www.apache.org/licenses/LICENSE-2.0
#
# Unless required by applicable law or agreed to in writing, software
# distributed under the License is distributed on an "AS IS" BASIS,
# WITHOUT WARRANTIES OR CONDITIONS OF ANY KIND, either express or implied.
# See the License for the specific language governing permissions and
# limitations under the License.

import argparse
import copy
import os
import random
import time

import torch
import numpy as np
import torch.distributed as dist
from apex import amp
from apex.optimizers import FusedLAMB
from apex.parallel import DistributedDataParallel

from common import helpers
from common.data.dali import sampler as dali_sampler
from common.data.dali.data_loader import DaliDataLoader
from common.data.text import Tokenizer
from common.data import features
from common.helpers import (Checkpointer, greedy_wer, num_weights, print_once,
                            process_evaluation_epoch)
from common.optimizers import lr_policy
from common.tb_dllogger import flush_log, init_log, log
from rnnt import config
from rnnt.decoder import RNNTGreedyDecoder
from rnnt.loss import RNNTLoss
from rnnt.model import RNNT

from mlperf import logging


# TODO Eval batch size

def parse_args():
    parser = argparse.ArgumentParser(description='RNN-T Training Reference')

    training = parser.add_argument_group('training setup')
    training.add_argument('--epochs', default=100, type=int,
                          help='Number of epochs for the entire training')
    training.add_argument("--warmup_epochs", default=6, type=int,
                          help='Initial epochs of increasing learning rate')
    training.add_argument("--hold_epochs", default=40, type=int,
                          help='Constant max learning rate epochs after warmup')
    training.add_argument('--epochs_this_job', default=0, type=int,
                          help=('Run for a number of epochs with no effect on the lr schedule.'
                                'Useful for re-starting the training.'))
    training.add_argument('--cudnn_benchmark', action='store_true', default=True,
                          help='Enable cudnn benchmark')
    training.add_argument('--amp', '--fp16', action='store_true', default=False,
                          help='Use mixed precision training')
    training.add_argument('--seed', default=None, type=int, help='Random seed')
    training.add_argument('--local_rank', default=os.getenv('LOCAL_RANK', 0), type=int,
                          help='GPU id used for distributed training')
    training.add_argument('--target', default=0.058, type=float, help='Target WER accuracy')

    optim = parser.add_argument_group('optimization setup')
    optim.add_argument('--batch_size', default=128, type=int,
                       help='Effective batch size per GPU (might require grad accumulation')
    optim.add_argument('--val_batch_size', default=2, type=int,
                       help='Evalution time batch size')
    optim.add_argument('--lr', default=4e-3, type=float,
                       help='Peak learning rate')
    optim.add_argument("--min_lr", default=1e-5, type=float,
                       help='minimum learning rate')
    optim.add_argument("--lr_exp_gamma", default=0.935, type=float,
                       help='gamma factor for exponential lr scheduler')
    optim.add_argument('--weight_decay', default=1e-3, type=float,
                       help='Weight decay for the optimizer')
    optim.add_argument('--grad_accumulation_steps', default=8, type=int,
                       help='Number of accumulation steps')
    optim.add_argument('--log_norm', action='store_true',
                       help='If enabled, gradient norms will be logged')
    optim.add_argument('--clip_norm', default=None, type=float,
                       help='If provided, gradients will be clipped above this norm')
    optim.add_argument('--beta1', default=0.9, type=float, help='Beta 1 for optimizer')
    optim.add_argument('--beta2', default=0.999, type=float, help='Beta 2 for optimizer')
    optim.add_argument('--ema', type=float, default=0.999,
                       help='Discount factor for exp averaging of model weights')

    io = parser.add_argument_group('feature and checkpointing setup')
    io.add_argument('--dali_device', type=str, choices=['cpu', 'gpu'],
                    default='cpu', help='Use DALI pipeline for fast data processing')
    io.add_argument('--resume', action='store_true',
                    help='Try to resume from last saved checkpoint.')
    io.add_argument('--ckpt', default=None, type=str,
                    help='Path to a checkpoint for resuming training')
    io.add_argument('--save_at_the_end', action='store_true',
                    help='Saves model checkpoint at the end of training')
    io.add_argument('--save_frequency', default=None, type=int,
                    help='Checkpoint saving frequency in epochs')
    io.add_argument('--keep_milestones', default=[], type=int, nargs='+',
                    help='Milestone checkpoints to keep from removing')
    io.add_argument('--save_best_from', default=200, type=int,
                    help='Epoch on which to begin tracking best checkpoint (dev WER)')
    io.add_argument('--val_frequency', default=1, type=int,
                    help='Number of epochs between evaluations on dev set')
    io.add_argument('--log_frequency', default=25, type=int,
                    help='Number of steps between printing training stats')
    io.add_argument('--prediction_frequency', default=None, type=int,
                    help='Number of steps between printing sample decodings')
    io.add_argument('--model_config', default='configs/baseline_v3-1023sp.yaml',
                    type=str, required=True,
                    help='Path of the model configuration file')
    io.add_argument('--num_buckets', type=int, default=6,
                    help='If provided, samples will be grouped by audio duration, '
                         'to this number of backets, for each bucket, '
                         'random samples are batched, and finally '
                         'all batches are randomly shuffled')
    io.add_argument('--train_manifests', type=str, required=True, nargs='+',
                    help='Paths of the training dataset manifest file')
    io.add_argument('--val_manifests', type=str, required=True, nargs='+',
                    help='Paths of the evaluation datasets manifest files')
    io.add_argument('--max_duration', type=float,
                    help='Discard samples longer than max_duration')
    io.add_argument('--dataset_dir', required=True, type=str,
                    help='Root dir of dataset')
    io.add_argument('--output_dir', type=str, required=True,
                    help='Directory for logs and checkpoints')
    io.add_argument('--log_file', type=str, default=None,
                    help='Path to save the training logfile.')
    io.add_argument('--no_old_eval', default=False, action='store_false',
                    help='Eval dataset is wrapped to fill the last batch')
    io.add_argument('--new_eval', action='store_true',
                    help='Eval on every sample once')
    return parser.parse_args()


def apply_ema(model, ema_model, decay):
    if not decay:
        return

    sd = getattr(model, 'module', model).state_dict()
    for k, v in ema_model.state_dict().items():
        v.copy_(decay * v + (1 - decay) * sd[k])


@torch.no_grad()
def evaluate(epoch, step, val_loaders, val_feat_proc, detokenize,
             ema_model, loss_fn, greedy_decoder, use_amp):

    ema_model.eval()

    for val_loader in val_loaders:
        start_time = time.time()
        agg = {'losses': [], 'preds': [], 'txts': [], 'idx': []}
        logging.log_start(logging.constants.EVAL_START,
                          metadata=dict(epoch_num=epoch, pipeline=val_loader.pipeline_type))
        for i, batch in enumerate(val_loader):
            print(f'{val_loader.pipeline_type} evaluation: {i:>10}/{len(val_loader):<10}', end='\r')

            audio, audio_lens, txt, txt_lens = batch

            feats, feat_lens = val_feat_proc([audio, audio_lens])

            log_probs, log_prob_lens = ema_model(feats, feat_lens, txt, txt_lens)
            loss = loss_fn(log_probs[:, :log_prob_lens.max().item()],
                                      log_prob_lens, txt, txt_lens)

            pred = greedy_decoder.decode(ema_model, feats, feat_lens)

            agg['losses'] += helpers.gather_losses([loss.cpu()])
            agg['preds'] += helpers.gather_predictions([pred], detokenize)
            agg['txts'] += helpers.gather_transcripts([txt.cpu()], [txt_lens.cpu()], detokenize)

        wer, loss = process_evaluation_epoch(agg)

        logging.log_event(logging.constants.EVAL_ACCURACY,
                          value=wer,
                          metadata=dict(epoch_num=epoch, pipeline=val_loader.pipeline_type))
        logging.log_end(logging.constants.EVAL_STOP,
                        metadata=dict(epoch_num=epoch, pipeline=val_loader.pipeline_type))

        log((epoch,), step, val_loader.pipeline_type, {'loss': loss, 'wer': 100.0 * wer,
                                     'took': time.time() - start_time})
    ema_model.train()
    return wer


def main():
    logging.configure_logger('RNNT')
    logging.log_start(logging.constants.INIT_START)

    args = parse_args()

    assert(torch.cuda.is_available())
    assert args.prediction_frequency is None or args.prediction_frequency % args.log_frequency == 0

    torch.backends.cudnn.benchmark = args.cudnn_benchmark

    # set up distributed training
    multi_gpu = int(os.environ.get('WORLD_SIZE', 1)) > 1
    if multi_gpu:
        torch.cuda.set_device(args.local_rank)
        dist.init_process_group(backend='nccl', init_method='env://')
        world_size = dist.get_world_size()
        print_once(f'Distributed training with {world_size} GPUs\n')
    else:
        world_size = 1

    if args.seed is not None:
        logging.log_event(logging.constants.SEED, value=args.seed)
        torch.manual_seed(args.seed + args.local_rank)
        np.random.seed(args.seed + args.local_rank)
        random.seed(args.seed + args.local_rank)
        # np_rng is used for buckets generation, and needs the same seed on every worker
        np_rng = np.random.default_rng(seed=args.seed)

    init_log(args)

    cfg = config.load(args.model_config)
    config.apply_duration_flags(cfg, args.max_duration)

    assert args.grad_accumulation_steps >= 1
    assert args.batch_size % args.grad_accumulation_steps == 0, f'{args.batch_size} % {args.grad_accumulation_steps} != 0'
    logging.log_event('gradient_accumulation_steps', value=args.grad_accumulation_steps)
    batch_size = args.batch_size // args.grad_accumulation_steps

    logging.log_event(logging.constants.SUBMISSION_BENCHMARK, value='RNN-T')
    logging.log_event(logging.constants.SUBMISSION_ORG, value='my-organization')
    logging.log_event(logging.constants.SUBMISSION_DIVISION, value='closed/open')
    logging.log_event(logging.constants.SUBMISSION_STATUS, value='onprem/cloud/research')
    logging.log_event(logging.constants.SUBMISSION_PLATFORM, value='my platform')

    logging.log_end(logging.constants.INIT_STOP)
    if multi_gpu:
        torch.distributed.barrier()
    logging.log_start(logging.constants.RUN_START)
    if multi_gpu:
        torch.distributed.barrier()

    print_once('Setting up datasets...')
    (
        train_dataset_kw,
        train_features_kw,
        train_splicing_kw,
        train_specaugm_kw,
    ) = config.input(cfg, 'train')
    (
        val_dataset_kw,
        val_features_kw,
        val_splicing_kw,
        val_specaugm_kw,
    ) = config.input(cfg, 'val')

    logging.log_event(logging.constants.MAX_SEQUENCE_LENGTH,
                      value=train_dataset_kw['max_duration'])
    logging.log_event('data_speed_perturbation_max',
                      value=train_dataset_kw['speed_perturbation']['max_rate'])
    logging.log_event('data_speed_perturbation_min',
                      value=train_dataset_kw['speed_perturbation']['min_rate'])
    logging.log_event('data_spec_augment_freq_n',
                      value=train_specaugm_kw['freq_masks'])
    logging.log_event('data_spec_augment_freq_min',
                      value=train_specaugm_kw['min_freq'])
    logging.log_event('data_spec_augment_freq_max',
                      value=train_specaugm_kw['max_freq'])
    logging.log_event('data_spec_augment_time_n',
                      value=train_specaugm_kw['time_masks'])
    logging.log_event('data_spec_augment_time_min',
                      value=train_specaugm_kw['min_time'])
    logging.log_event('data_spec_augment_time_max',
                      value=train_specaugm_kw['max_time'])
    logging.log_event(logging.constants.GLOBAL_BATCH_SIZE,
                      value=batch_size * world_size * args.grad_accumulation_steps)

    tokenizer_kw = config.tokenizer(cfg)
    tokenizer = Tokenizer(**tokenizer_kw)

    class PermuteAudio(torch.nn.Module):
        def forward(self, x):
            return (x[0].permute(2, 0, 1), *x[1:])

    train_augmentations = torch.nn.Sequential(
        train_specaugm_kw and features.SpecAugment(optim_level=args.amp, **train_specaugm_kw) or torch.nn.Identity(),
        features.FrameSplicing(optim_level=args.amp, **train_splicing_kw),
        features.FillPadding(optim_level=args.amp, ),
        PermuteAudio(),
    )
    val_augmentations = torch.nn.Sequential(
        val_specaugm_kw and features.SpecAugment(optim_level=args.amp, **val_specaugm_kw) or torch.nn.Identity(),
        features.FrameSplicing(optim_level=args.amp, **val_splicing_kw),
        features.FillPadding(optim_level=args.amp, ),
        PermuteAudio(),
    )

    logging.log_event('num_buckets', value=args.num_buckets)

    if args.num_buckets is not None:
        sampler = dali_sampler.BucketingSampler(
            args.num_buckets,
            batch_size,
            world_size,
            args.epochs,
            np_rng
        )
    else:
        sampler = dali_sampler.SimpleSampler()

    train_loader = DaliDataLoader(gpu_id=args.local_rank,
                                  dataset_path=args.dataset_dir,
                                  config_data=train_dataset_kw,
                                  config_features=train_features_kw,
                                  json_names=args.train_manifests,
                                  batch_size=batch_size,
                                  sampler=sampler,
                                  grad_accumulation_steps=args.grad_accumulation_steps,
                                  pipeline_type="train",
                                  device_type=args.dali_device,
                                  tokenizer=tokenizer)

    val_loaders = []
    if not args.no_old_eval:
        val_loaders.append(DaliDataLoader(gpu_id=args.local_rank,
                                    dataset_path=args.dataset_dir,
                                    config_data=val_dataset_kw,
                                    config_features=val_features_kw,
                                    json_names=args.val_manifests,
                                    batch_size=args.val_batch_size,
                                    sampler=dali_sampler.SimpleSampler(),
                                    pipeline_type="old_val",
                                    device_type=args.dali_device,
                                    tokenizer=tokenizer))
    if args.new_eval:
        val_loaders.append(DaliDataLoader(gpu_id=args.local_rank,
                                    dataset_path=args.dataset_dir,
                                    config_data=val_dataset_kw,
                                    config_features=val_features_kw,
                                    json_names=args.val_manifests,
                                    batch_size=args.val_batch_size,
                                    sampler=dali_sampler.SimpleSampler(),
                                    pipeline_type="new_val",
                                    device_type=args.dali_device,
                                    tokenizer=tokenizer))

    train_feat_proc = train_augmentations
    val_feat_proc   = val_augmentations

    train_feat_proc.cuda()
    val_feat_proc.cuda()

    steps_per_epoch = len(train_loader) // args.grad_accumulation_steps

    logging.log_event(logging.constants.TRAIN_SAMPLES, value=train_loader.dataset_size)
    logging.log_event(logging.constants.EVAL_SAMPLES, value=val_loaders[0].dataset_size)

    # set up the model
    model = RNNT(n_classes=tokenizer.num_labels + 1, **config.rnnt(cfg))
    model.cuda()
    blank_idx = tokenizer.num_labels
    loss_fn = RNNTLoss(blank_idx=blank_idx)
    greedy_decoder = RNNTGreedyDecoder(blank_idx=blank_idx)

    print_once(f'Model size: {num_weights(model) / 10**6:.1f}M params\n')

    logging.log_event(logging.constants.OPT_NAME, value='lamb')
    logging.log_event(logging.constants.OPT_BASE_LR, value=args.lr)
    logging.log_event('opt_epsilon', value=1e-9)
    logging.log_event('opt_learning_rate_exp_gamma', value=args.lr_exp_gamma)
    logging.log_event('opt_learning_rate_warmup_epochs', value=args.warmup_epochs)
    logging.log_event('opt_hold_learning_rate_epochs', value=args.hold_epochs)
    logging.log_event('opt_beta1', value=args.beta1)
    logging.log_event('opt_beta2', value=args.beta2)
    logging.log_event('clip_norm', value=args.clip_norm)
    logging.log_event(logging.constants.OPT_LR_ALT_DECAY_FUNC, value=True)
    logging.log_event(logging.constants.OPT_LR_ALT_WARMUP_FUNC, value=True)
    logging.log_event('min_learning_rate', value=args.min_lr)

    # optimization
    kw = {'params': model.param_groups(args.lr), 'lr': args.lr,
          'weight_decay': args.weight_decay}

    initial_lrs = [group['lr'] for group in kw['params']]

    print_once(f'Starting with LRs: {initial_lrs}')
    optimizer = FusedLAMB(betas=(args.beta1, args.beta2), eps=1e-9, **kw)

    adjust_lr = lambda step, epoch: lr_policy(
        step, epoch, initial_lrs, optimizer, steps_per_epoch=steps_per_epoch,
        warmup_epochs=args.warmup_epochs, hold_epochs=args.hold_epochs,
        min_lr=args.min_lr, exp_gamma=args.lr_exp_gamma)

    if args.amp:
        model, optimizer = amp.initialize(
            models=model,
            optimizers=optimizer,
            opt_level='O1',
            max_loss_scale=512.0)

    if args.ema > 0:
        ema_model = copy.deepcopy(model).cuda()
    else:
        ema_model = None
    logging.log_event('ema_factor', value=args.ema)

    if multi_gpu:
        model = DistributedDataParallel(model)

    # load checkpoint
    meta = {'best_wer': 10**6, 'start_epoch': 0}
    checkpointer = Checkpointer(args.output_dir, 'RNN-T',
                                args.keep_milestones, args.amp)
    if args.resume:
        args.ckpt = checkpointer.last_checkpoint() or args.ckpt

    if args.ckpt is not None:
        checkpointer.load(args.ckpt, model, ema_model, optimizer, meta)

    start_epoch = meta['start_epoch']
    best_wer = meta['best_wer']
    last_wer = meta['best_wer']
    epoch = 1
    step = start_epoch * steps_per_epoch + 1

    # training loop
    model.train()
    for epoch in range(start_epoch + 1, args.epochs + 1):

        logging.log_start(logging.constants.BLOCK_START,
                          metadata=dict(first_epoch_num=epoch,
                                        epoch_count=1))
        logging.log_start(logging.constants.EPOCH_START,
                          metadata=dict(epoch_num=epoch))

        epoch_utts = 0
        accumulated_batches = 0
        epoch_start_time = time.time()

        for batch in train_loader:

            if accumulated_batches == 0:
                adjust_lr(step, epoch)
                optimizer.zero_grad()
                step_utts = 0
                step_start_time = time.time()
                all_feat_lens = []

            audio, audio_lens, txt, txt_lens = batch

            feats, feat_lens = train_feat_proc([audio, audio_lens])
            all_feat_lens += feat_lens

            log_probs, log_prob_lens = model(feats, feat_lens, txt, txt_lens)
            loss = loss_fn(log_probs[:, :log_prob_lens.max().item()],
                                      log_prob_lens, txt, txt_lens)

            loss /= args.grad_accumulation_steps

            del log_probs, log_prob_lens

            if torch.isnan(loss).any():
                print_once(f'WARNING: loss is NaN; skipping update')
            else:
                if args.amp:
                    with amp.scale_loss(loss, optimizer) as scaled_loss:
                        scaled_loss.backward()
                else:
                    loss.backward()
                loss_item = loss.item()
                del loss
                step_utts += batch[0].size(0) * world_size
                epoch_utts += batch[0].size(0) * world_size
                accumulated_batches += 1

            if accumulated_batches % args.grad_accumulation_steps == 0:

                if args.clip_norm is not None:
                    torch.nn.utils.clip_grad_norm_(
                        getattr(model, 'module', model).parameters(),
                        max_norm=args.clip_norm,
                        norm_type=2)

                total_norm = 0.0

                try:
                    if args.log_norm:
                        for p in getattr(model, 'module', model).parameters():
                            param_norm = p.grad.data.norm(2)
                            total_norm += param_norm.item() ** 2
                        total_norm = total_norm ** (1. / 2)
                except AttributeError as e:
                    print_once(f'Exception happened: {e}')
                    total_norm = 0.0

                optimizer.step()
                apply_ema(model, ema_model, args.ema)

                if step % args.log_frequency == 0:

                    if args.prediction_frequency is None or step % args.prediction_frequency == 0:
                        preds = greedy_decoder.decode(model, feats, feat_lens)
                        wer, pred_utt, ref = greedy_wer(
                                preds,
                                txt,
                                txt_lens,
                                tokenizer.detokenize)
                        print_once(f'  Decoded:   {pred_utt[:90]}')
                        print_once(f'  Reference: {ref[:90]}')
                        wer = {'wer': 100 * wer}
                    else:
                        wer = {}

                    step_time = time.time() - step_start_time

                    log((epoch, step % steps_per_epoch or steps_per_epoch, steps_per_epoch),
                        step, 'train',
                        {'loss': loss_item,
                         **wer,  # optional entry
                         'throughput': step_utts / step_time,
                         'took': step_time,
                         'grad-norm': total_norm,
                         'seq-len-min': min(all_feat_lens).item(),
                         'seq-len-max': max(all_feat_lens).item(),
                         'lrate': optimizer.param_groups[0]['lr']})

                step_start_time = time.time()

                step += 1
                accumulated_batches = 0
                # end of step

        logging.log_end(logging.constants.EPOCH_STOP,
                        metadata=dict(epoch_num=epoch))

        epoch_time = time.time() - epoch_start_time
        log((epoch,), None, 'train_avg', {'throughput': epoch_utts / epoch_time,
                                          'took': epoch_time})

        if epoch % args.val_frequency == 0:
            wer = evaluate(epoch, step, val_loaders, val_feat_proc,
                           tokenizer.detokenize, ema_model, loss_fn,
                           greedy_decoder, args.amp)

            last_wer = wer
            if wer < best_wer and epoch >= args.save_best_from:
                checkpointer.save(model, ema_model, optimizer, epoch,
                                  step, best_wer, is_best=True)
                best_wer = wer

        save_this_epoch = (args.save_frequency is not None and epoch % args.save_frequency == 0) \
                       or (epoch in args.keep_milestones)
        if save_this_epoch:
            checkpointer.save(model, ema_model, optimizer, epoch, step, best_wer)

        logging.log_end(logging.constants.BLOCK_STOP, metadata=dict(first_epoch_num=epoch))

        if last_wer <= args.target:
            logging.log_end(logging.constants.RUN_STOP, metadata={'status': 'success'})
            print_once(f'Finished after {args.epochs_this_job} epochs.')
            break
        if 0 < args.epochs_this_job <= epoch - start_epoch:
            print_once(f'Finished after {args.epochs_this_job} epochs.')
            break
        # end of epoch

    log((), None, 'train_avg', {'throughput': epoch_utts / epoch_time})

    if last_wer > args.target:
        logging.log_end(logging.constants.RUN_STOP, metadata={'status': 'aborted'})

    if epoch == args.epochs:
        evaluate(epoch, step, val_loaders, val_feat_proc, tokenizer.detokenize,
                 ema_model, loss_fn, greedy_decoder, args.amp)

    flush_log()
    if args.save_at_the_end:
        checkpointer.save(model, ema_model, optimizer, epoch, step, best_wer)


if __name__ == "__main__":
    main()
