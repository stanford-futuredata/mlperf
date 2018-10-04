# Copyright 2018 MLBenchmark Group. All Rights Reserved.
#
# Licensed under the Apache License, Version 2.0 (the "License");
# you may not use this file except in compliance with the License.
# You may obtain a copy of the License at
#
#     http://www.apache.org/licenses/LICENSE-2.0
#
# Unless required by applicable law or agreed to in writing, software
# distributed under the License is distributed on an "AS IS" BASIS,
# WITHOUT WARRANTIES OR CONDITIONS OF ANY KIND, either express or implied.
# See the License for the specific language governing permissions and
# limitations under the License.
# ==============================================================================
"""Master list of MLPerf tags to be logged for benchmark submissions.
"""

from __future__ import absolute_import
from __future__ import division
from __future__ import print_function

from _ncf_tags import *

# ==============================================================================
# == Benchmarks ================================================================
# ==============================================================================

# recommendation/
NCF = "ncf"

# translation/
TRANSFORMER = "transformer"

# ==============================================================================
# == Tags ======================================================================
# ==============================================================================
"""
Tags may be used by all models, a subset of models, or only one model. A
specification for which models require which tags can be found below the tag
definitions.
"""

# \\\\\\\\\\\\\\\\\\\\\\\\\\\\\\\\\\\\\\\\\\\\\\\\\\\\\\\\\\\\\\\\\\\\\\\\\\\\\\
# All models: Tags which should appear in absolutely every MLPerf model.
# //////////////////////////////////////////////////////////////////////////////

# This tag signals to start the timer. Emission of this tag need not be (and
# generally will not be) the first part of a submission script. Rather, this
# tag must be emitted prior to performing any work which the MLPerf rules
# state must be timed. This tag is generally emitted directly before the first
# step which invokes random number generation or the first step which must be
# performed on the system under test. (Whichever comes first.) If clarification
# is needed, please file an issue under:
#   https://github.com/mlperf/policies
RUN_START = "run_start"

# This tag signals that a submission has reached the relevant stopping criteria,
# and has completed all tasks which are performed in the reference. The wall
# time for a submission will be computed as the difference between the time
# when this tag is emitted and the time whe the RUN_START is emitted.
RUN_STOP = "run_stop"

# This tag should be emitted immediately before ending a run, and should be the
# last tag emitted. This tag should indicate the completion of untimed post
# processing work such as system specific cleanup.
RUN_FINAL = "run_final"


# \\\\\\\\\\\\\\\\\\\\\\\\\\\\\\\\\\\\\\\\\\\\\\\\\\\\\\\\\\\\\\\\\\\\\\\\\\\\\\
# Common Values: Constants which are expected to be reported across many models.
#                These values are included for convenience.
# //////////////////////////////////////////////////////////////////////////////
BCE = "binary_cross_entropy"
CCE = "categorical_cross_entropy"


# \\\\\\\\\\\\\\\\\\\\\\\\\\\\\\\\\\\\\\\\\\\\\\\\\\\\\\\\\\\\\\\\\\\\\\\\\\\\\\
# Preprocessing: Tags for generic preprocessing steps
# //////////////////////////////////////////////////////////////////////////////

# The number of training examples in a single epoch
PREPROC_NUM_TRAIN_EXAMPLES = "preproc_num_train_examples"

# The number of evaluation examples in a single epoch
PREPROC_NUM_EVAL_EXAMPLES = "preproc_num_eval_examples"

# This tag is used to declare what part of code tokenizes the training data.
PREPROC_TOKENIZE_TRAINING = "preproc_tokenize_training"

# This tag is used to declare what part of code tokenizes the evaluation data.
PREPROC_TOKENIZE_EVAL = "preproc_tokenize_eval"

# The vocabulary size used for tokenization.
PREPROC_VOCAB_SIZE = "preproc_vocab_size"


# \\\\\\\\\\\\\\\\\\\\\\\\\\\\\\\\\\\\\\\\\\\\\\\\\\\\\\\\\\\\\\\\\\\\\\\\\\\\\\
# Input: Tags for the timed portion of the data input pipeline
# //////////////////////////////////////////////////////////////////////////////

# The number of examples in the training portion of the data pipeline. Generally
# this should match PREPROC_NUM_TRAIN_EXAMPLES. If it does not (for instance
# if certain examples are dropped in compliance with MLPerf rules), the
# call which declares this tag is a good place for a comment stating why the
# disparity is expected.
INPUT_SIZE = "input_size"

# The size of a training minibatch size. If this value is variable, please emit
# "-1" and then log an implementation specific characterization of the batch
# size which is a reasonable analog to the reference. (For instance log that
# all but the last batch has size 64, and the last batch is a partial batch)
INPUT_BATCH_SIZE = "input_batch_size"

# This tag indicates where the location of the code which defines the order in
# which training examples are traversed. It is not necessary to describe the
# method in the tag emission (though comments are always welcome). Rather, this
# should simply provide a good starting point to an interested party.
INPUT_ORDER = "input_order"


# \\\\\\\\\\\\\\\\\\\\\\\\\\\\\\\\\\\\\\\\\\\\\\\\\\\\\\\\\\\\\\\\\\\\\\\\\\\\\\
# Opt: Tags for declaring optimizer specific information. Submissions should
#      declare and log explicit values rather than relying on defaults.
# //////////////////////////////////////////////////////////////////////////////

# The name of the optimizer used. (SGD, Adam, etc.)
OPT_NAME = "opt_name"

OPT_LR = "learning_rate"

# beta1, beta2, and epsilon are optimizer hyperparameters associated with the
# Adam optimizer and its variants (e.g. LazyAdam).
OPT_HP_ADAM_BETA1 = "opt_hp_Adam_beta1"
OPT_HP_ADAM_BETA2 = "opt_hp_Adam_beta2"
OPT_HP_ADAM_EPSILON = "opt_hp_Adam_epsilon"


# \\\\\\\\\\\\\\\\\\\\\\\\\\\\\\\\\\\\\\\\\\\\\\\\\\\\\\\\\\\\\\\\\\\\\\\\\\\\\\
#  Train: Tags for control flow during model training.
# //////////////////////////////////////////////////////////////////////////////

# This tag is emitted when a model first enters its training loop. This is not
# necessarily when it begins to apply gradients; rather, it should be placed at
# a location which logically partitions the submission code.
TRAIN_LOOP = "train_loop"

# The current epoch as said epoch begins training.
TRAIN_EPOCH = "train_epoch"

# The current learning rate at the start of each epoch.
TRAIN_LEARN_RATE = "train_learn_rate"

# This tag is used to indicate approximately where checkpoints are written. Some
# frameworks abstract away checkpoint saving; in such cases simply choose a
# logical place in the code which signals that the framework has been instructed
# to save checkpoints, along with an explanatory comment.
TRAIN_CHECKPOINT = "train_checkpoint"


# \\\\\\\\\\\\\\\\\\\\\\\\\\\\\\\\\\\\\\\\\\\\\\\\\\\\\\\\\\\\\\\\\\\\\\\\\\\\\\
#  Eval: Tags for control flow during model evaluation.
# //////////////////////////////////////////////////////////////////////////////

# This tag should be emitted whenever the submission begins an evaluation pass
# for a given set of weights.
EVAL_START = "eval_start"

# The number of examples on which evaluation is performed.
EVAL_SIZE = "eval_size"

# The target quality at which the model may stop training.
EVAL_TARGET = "eval_target"

# The observed accuracy of the model at a given epoch.
EVAL_ACCURACY = "eval_accuracy"

# This tag should be emitted when the model has determined that it has met the
# target quality set by the reference.
EVAL_STOP = "eval_stop"


# \\\\\\\\\\\\\\\\\\\\\\\\\\\\\\\\\\\\\\\\\\\\\\\\\\\\\\\\\\\\\\\\\\\\\\\\\\\\\\
#  Model: Tags for logging topology specific information.
# //////////////////////////////////////////////////////////////////////////////

# The loss function (cross entropy, squared error, etc.) used by the model. For
# more exotic loss functions such as those encountered in object detection
# models, additional benchmark specific subcomponents should also be logged.
MODEL_HP_LOSS_FN = "model_hp_loss_fn"


# ==============================================================================
# == Benchmark tag sets ========================================================
# ==============================================================================

NCF_TAGS = (
    RUN_START,
    RUN_STOP,
    RUN_FINAL,

    PREPROC_HP_MIN_RATINGS,
    PREPROC_HP_NUM_EVAL,
    PREPROC_HP_SAMPLE_EVAL_REPLACEMENT,

    INPUT_SIZE,
    INPUT_BATCH_SIZE,
    INPUT_ORDER,
    INPUT_HP_NUM_NEG,
    INPUT_HP_SAMPLE_TRAIN_REPLACEMENT,
    INPUT_STEP_TRAIN_NEG_GEN,
    INPUT_STEP_EVAL_NEG_GEN,

    OPT_NAME,
    OPT_LR,
    OPT_HP_ADAM_BETA1,
    OPT_HP_ADAM_BETA2,
    OPT_HP_ADAM_EPSILON,

    TRAIN_LOOP,
    TRAIN_EPOCH,
    TRAIN_LEARN_RATE,

    EVAL_START,
    EVAL_SIZE,
    EVAL_TARGET,
    EVAL_ACCURACY,
    EVAL_STOP,
    EVAL_HP_NUM_USERS,
    EVAL_HP_NUM_NEG,

    MODEL_HP_LOSS_FN,
    MODEL_HP_MF_DIM,
    MODEL_HP_MLP_LAYER_SIZES,
)

