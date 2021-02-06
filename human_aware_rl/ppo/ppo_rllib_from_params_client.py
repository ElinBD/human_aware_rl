# Warning: Please note that although this file looks very similar to ppo_rllib_client.py, but very different
# You should use this file if you plan to generate mdp from a set of mdp generating parameters

# All imports except rllib
import argparse, os, sys
from overcooked_ai_py.agents.benchmarking import AgentEvaluator
import numpy as np

# environment variable that tells us whether this code is running on the server or not
LOCAL_TESTING = os.getenv('RUN_ENV', 'production') == 'local'

# Sacred setup (must be before rllib imports)
from sacred import Experiment
ex_fp = Experiment("PPO RLLib From Params")

# Necessary work-around to make sacred pickling compatible with rllib
from sacred import SETTINGS
SETTINGS.CONFIG.READ_ONLY_CONFIG = False

# Slack notification configuration
from sacred.observers import SlackObserver
if os.path.exists('slack.json') and not LOCAL_TESTING:
    slack_obs = SlackObserver.from_config('slack.json')
    ex_fp.observers.append(slack_obs)

    # Necessary for capturing stdout in multiprocessing setting
    SETTINGS.CAPTURE_MODE = 'sys'

# rllib and rllib-dependent imports
# Note: tensorflow and tensorflow dependent imports must also come after rllib imports
# This is because rllib disables eager execution. Otherwise, it must be manually disabled
import ray
from ray.tune.result import DEFAULT_RESULTS_DIR
from ray.tune.registry import register_env
from ray.rllib.models import ModelCatalog
from ray.rllib.agents.ppo.ppo import PPOTrainer
from human_aware_rl.ppo.ppo_rllib import RllibPPOModel, RllibLSTMPPOModel
from human_aware_rl.rllib.rllib import OvercookedMultiAgent, save_trainer, gen_trainer_from_params, load_trainer
from human_aware_rl.imitation.behavior_cloning_tf2 import BehaviorCloningPolicy, BC_SAVE_DIR


###################### Temp Documentation #######################
#   run the following command in order to train a PPO self-play #
#   agent with the static parameters listed in my_config        #
#                                                               #
#   python ppo_rllib_client.py                                  #
#                                                               #
#   In order to view the results of training, run the following #
#   command                                                     #
#                                                               #
#   tensorboard --log-dir ~/ray_results/                        #
#                                                               #
#################################################################

# Dummy wrapper to pass rllib type checks
def _env_creator(env_config):
    # Re-import required here to work with serialization
    from human_aware_rl.rllib.rllib import OvercookedMultiAgent 
    return OvercookedMultiAgent.from_config(env_config)


@ex_fp.config
def my_config():
    ### Resume chekpoint_path ###
    resume_checkpoint_path = None

    ### Model params ###

    # whether to use recurrence in ppo model
    use_lstm = False

    # Base model params
    NUM_HIDDEN_LAYERS = 3
    SIZE_HIDDEN_LAYERS = 64
    NUM_FILTERS = 25
    NUM_CONV_LAYERS = 3

    # LSTM memory cell size (only used if use_lstm=True)
    CELL_SIZE = 256



    ### Training Params ###

    num_workers = 20 if not LOCAL_TESTING else 2

    # list of all random seeds to use for experiments, used to reproduce results
    seeds = [0]

    # Placeholder for random for current trial
    seed = None

    # Number of gpus the central driver should use
    num_gpus = 1 if not LOCAL_TESTING else 0

    # How many environment timesteps will be simulated (across all environments)
    # for one set of gradient updates. Is divided equally across environments
    # train_batch_size = 40000 if not LOCAL_TESTING else 800
    train_batch_size = 128000 if not LOCAL_TESTING else 800

    # size of minibatches we divide up each batch into before
    # performing gradient steps
    # sgd_minibatch_size = 10000 if not LOCAL_TESTING else 800
    sgd_minibatch_size = 80000 if not LOCAL_TESTING else 800

    # Rollout length
    rollout_fragment_length = 400
    
    # Whether all PPO agents should share the same policy network
    shared_policy = True

    # Number of training iterations to run
    num_training_iters = 1000 if not LOCAL_TESTING else 2

    # Stepsize of SGD.
    lr = 7e-4

    # Learning rate schedule.
    lr_schedule = None

    # If specified, clip the global norm of gradients by this amount
    grad_clip = 0.1

    # Discount factor
    gamma = 0.99

    # Exponential decay factor for GAE (how much weight to put on monte carlo samples)
    # Reference: https://arxiv.org/pdf/1506.02438.pdf
    lmbda = 0.98

    # Whether the value function shares layers with the policy model
    vf_share_layers = True

    # How much the loss of the value network is weighted in overall loss
    vf_loss_coeff = 1e-4

    # Entropy bonus coefficient, will anneal linearly from _start to _end over _horizon steps
    entropy_coeff_start = 0.2
    entropy_coeff_end = 0.0005
    entropy_coeff_horizon = 4e8

    # Initial coefficient for KL divergence.
    kl_coeff = 0.2

    # PPO clipping factor
    clip_param = 0.05

    # Number of SGD iterations in each outer loop (i.e., number of epochs to
    # execute per train batch).
    num_sgd_iter = 8 if not LOCAL_TESTING else 1

    # How many trainind iterations (calls to trainer.train()) to run before saving model checkpoint
    save_freq = 250

    # How many training iterations to run between each evaluation
    evaluation_interval = 200 if not LOCAL_TESTING else 1

    # How many timesteps should be in an evaluation episode
    evaluation_ep_length = 400

    # Number of games to simulation each evaluation
    evaluation_num_games = 2

    # Whether to display rollouts in evaluation
    evaluation_display = True

    # Where to store replay txt files
    evaluation_replay_store_dir = None

    # Where to log the ray dashboard stats
    temp_dir = os.path.join(os.path.abspath(os.sep), "tmp", "ray_tmp") if not LOCAL_TESTING else None

    # Where to store model checkpoints and training stats
    results_dir = DEFAULT_RESULTS_DIR

    # Whether tensorflow should execute eagerly or not
    eager = False


    ### BC Params ###
    # path to pickled policy model for behavior cloning
    bc_model_dir = os.path.join(BC_SAVE_DIR, "default")

    # Whether bc agents should return action logit argmax or sample
    bc_stochastic = True


    ## MDP Generator Params ###
    # What is the shape of the inner mdp
    inner_shape = (5, 4)

    # What proportion of the inner mdp is empty
    prop_empty = 0.95

    # What proportion of the inner mdp has features (Onion, Tomato, Pot, etc..)
    prop_feats = 0.1


    ### Environment Params ###

    outer_shape = (5, 4)

    # Littering parameters
    onion_litter = 0.0
    dish_litter = 0.0
    soup_1_litter = 0.0
    soup_2_litter = 0.0
    soup_3_litter = 0.0
    pot_litter = 0.0
    player_litter = 0.0
    litter_fraction = 0.0
    littered = str(sum([onion_litter, dish_litter, soup_1_litter, soup_2_litter, soup_3_litter, pot_litter, player_litter]) > 0 and litter_fraction > 0)

    params_str = "nw=%d_vf=%f_es=%f_en=%f_kl=%f_outer_shape=%d_%d--inner_shape=%d_%d--prop_empty=%f--prop_feats=%f--littered=%s" % (
        num_workers,
        vf_loss_coeff,
        entropy_coeff_start,
        entropy_coeff_end,
        kl_coeff,
        outer_shape[0],
        outer_shape[1],
        inner_shape[0],
        inner_shape[1],
        prop_empty,
        prop_feats,
        littered
    )

    # Name of directory to store training results in (stored in ~/ray_results/<experiment_name>)
    experiment_name = "{0}_{1}".format("PPO_fp_", params_str)

    # Whether dense reward should come from potential function or not
    use_phi = False

    # Max episode length
    horizon = 400

    # The number of MDP in the env.mdp_lst
    num_mdp = 1
    # num_mdp = np.inf  # for infinite mdp

    # Constant by which shaped rewards are multiplied by when calculating total reward
    reward_shaping_factor = 1.0

    # Linearly anneal the reward shaping factor such that it reaches zero after this number of timesteps
    reward_shaping_horizon = 2e8

    # bc_factor represents that ppo agent gets paired with a bc agent for any episode
    # schedule for bc_factor is represented by a list of points (t_i, v_i) where v_i represents the 
    # value of bc_factor at timestep t_i. Values are linearly interpolated between points
    # The default listed below represents bc_factor=0 for all timesteps
    bc_schedule = OvercookedMultiAgent.self_play_bc_schedule

    # To be passed into rl-lib model/custom_options config
    model_params = {
        "use_lstm" : use_lstm,
        "NUM_HIDDEN_LAYERS" : NUM_HIDDEN_LAYERS,
        "SIZE_HIDDEN_LAYERS" : SIZE_HIDDEN_LAYERS,
        "NUM_FILTERS" : NUM_FILTERS,
        "NUM_CONV_LAYERS" : NUM_CONV_LAYERS,
        "CELL_SIZE" : CELL_SIZE
    }

    # to be passed into the rllib.PPOTrainer class
    training_params = {
        "num_workers" : num_workers,
        "train_batch_size" : train_batch_size,
        "sgd_minibatch_size" : sgd_minibatch_size,
        "rollout_fragment_length" : rollout_fragment_length,
        "num_sgd_iter" : num_sgd_iter,
        "lr" : lr,
        "lr_schedule" : lr_schedule,
        "grad_clip" : grad_clip,
        "gamma" : gamma,
        "lambda" : lmbda,
        "vf_share_layers" : vf_share_layers,
        "vf_loss_coeff" : vf_loss_coeff,
        "kl_coeff" : kl_coeff,
        "clip_param" : clip_param,
        "num_gpus" : num_gpus,
        "seed" : seed,
        "evaluation_interval" : evaluation_interval,
        "entropy_coeff_schedule" : [(0, entropy_coeff_start), (entropy_coeff_horizon, entropy_coeff_end)],
        "eager" : eager
    }

    # To be passed into AgentEvaluator constructor and _evaluate function
    evaluation_params = {
        "ep_length" : evaluation_ep_length,
        "num_games" : evaluation_num_games,
        "display" : evaluation_display,
        "store_dir" : evaluation_replay_store_dir,
        "display_phi": True
    }

    # Please note that this function cannot be pickled
    # However, the initial inner_shape, prop_empty, prop_feats will be pickled
    def params_schedule_fn(outside_information):
        """
        In this preliminary version, the outside information is ignored
        """
        # Rewards the agent will receive for intermediate actions
        rew_shaping_params = {
            "PLACEMENT_IN_POT_REW": 3,
            "DISH_PICKUP_REWARD": 3,
            "SOUP_PICKUP_REWARD": 5,
            "DISH_DISP_DISTANCE_REW": 0,
            "POT_DISTANCE_REW": 0,
            "SOUP_DISTANCE_REW": 0,
        }
        mdp_default_gen_params = {
            "inner_shape": outside_information["inner_shape"],
            "prop_empty": outside_information["prop_empty"],
            "prop_feats": outside_information["prop_feats"],
            "start_all_orders": [
                {"ingredients": ["onion", "onion", "onion"]}
            ],
            "display": False,
            "rew_shaping_params": rew_shaping_params
        }
        return mdp_default_gen_params


    environment_params = {
        # To be passed into OvercookedGridWorld constructor
        "outer_shape" : outer_shape,
        "mdp_params_schedule_fn" : params_schedule_fn,
        # To be passed into OvercookedEnv constructor
        "env_params" : {
            "horizon" : horizon,
            "num_mdp" : num_mdp,
            "initial_info": {
                "inner_shape": inner_shape,
                "prop_empty": prop_empty,
                "prop_feats": prop_feats
            },
            "litter_params" : {
                "onion_litter": onion_litter,
                "dish_litter": dish_litter,
                "soup_1_litter": soup_1_litter,
                "soup_2_litter": soup_2_litter,
                "soup_3_litter": soup_3_litter,
                "pot_litter": pot_litter,
                "player_litter": player_litter,
                "litter_fraction": litter_fraction
            }
        },

        # evaluation mdp params

        "eval_mdp_params" :{
            "inner_shape": inner_shape,
            "prop_empty": prop_empty,
            "prop_feats": prop_feats,
            "start_all_orders": [
                {"ingredients": ["onion", "onion", "onion"]}
            ],
            "display": False
        },

        
        #"eval_mdp_params" :{
        #    "layout_name": "cramped_room"
        #},

        # To be passed into OvercookedMultiAgent constructor
        "multi_agent_params" : {
            "reward_shaping_factor" : reward_shaping_factor,
            "reward_shaping_horizon" : reward_shaping_horizon,
            "use_phi" : use_phi,
            "bc_schedule" : bc_schedule
        }
    }

    bc_params = {
        "bc_policy_cls" : BehaviorCloningPolicy,
        "bc_config" : {
            "model_dir" : bc_model_dir,
            "stochastic" : bc_stochastic,
            "eager" : eager
        }
    }

    ray_params = {
        "custom_model_id" : "MyPPOModel",
        "custom_model_cls" : RllibLSTMPPOModel if model_params['use_lstm'] else RllibPPOModel,
        "temp_dir" : temp_dir,
        "env_creator" : _env_creator
    }

    params = {
        "model_params" : model_params,
        "training_params" : training_params,
        "environment_params" : environment_params,
        "bc_params" : bc_params,
        "shared_policy" : shared_policy,
        "num_training_iters" : num_training_iters,
        "evaluation_params" : evaluation_params,
        "experiment_name" : experiment_name,
        "save_every" : save_freq,
        "seeds" : seeds,
        "temp_dir" : temp_dir,
        "results_dir" : results_dir,
        "ray_params" : ray_params,
        "resume_checkpoint_path": resume_checkpoint_path
    }

# Dummy wrapper to pass rllib type checks
def _env_creater(env_config):
    return OvercookedMultiAgent.from_config(env_config)


def run(params):
    # reload checkpoint if it exist, and is not None
    if "resume_checkpoint_path" in params and params["resume_checkpoint_path"]:
        saved_path = params["resume_checkpoint_path"]
        trainer = load_trainer(save_path=saved_path, custom_config=params)
    else:
        # Retrieve the tune.Trainable object that is used for the experiment
        trainer = gen_trainer_from_params(params)

    # Object to store training results in
    result = {}

    # Training loop
    for i in range(params['num_training_iters']):
        print("Starting training iteration", i)
        result = trainer.train()

        if i % params['save_every'] == 0:
            save_path = save_trainer(trainer, params)
            print("saved trainer at", save_path)

    # Save the state of the experiment at end
    save_path = save_trainer(trainer, params)
    print("saved trainer at", save_path)

    return result


@ex_fp.automain
def main(params):
    # All ray environment set-up
    ray.init(temp_dir=params['temp_dir'])
    register_env("overcooked_multi_agent", _env_creater)
    ModelCatalog.register_custom_model("MyPPOModel", RllibLSTMPPOModel if params['model_params']['use_lstm'] else RllibPPOModel)

    # List of each random seed to run
    seeds = params['seeds']
    del params['seeds']

    # List to store results dicts (to be passed to sacred slack observer)
    results = []

    # Train an agent to completion for each random seed specified
    for seed in seeds:
        # Override the seed
        params['training_params']['seed'] = seed

        # Do the thing
        result = run(params)
        results.append(result)

    # Return value gets sent to our slack observer for notification
    average_sparse_reward = np.mean([res['custom_metrics']['sparse_reward_mean'] for res in results])
    average_episode_reward = np.mean([res['episode_reward_mean'] for res in results])
    return { "average_sparse_reward" : average_sparse_reward, "average_total_reward" : average_episode_reward }