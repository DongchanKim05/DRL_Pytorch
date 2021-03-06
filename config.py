# Config
import datetime
import torch

state_size = 19 * 4
action_size = 3

load_model = True
train_mode = False

batch_size = 128
mem_maxlen = 50000

discount_factor = 0.99
learning_rate = 0.0001

skip_frame = 1
stack_frame = 1

start_train_step = 25000
run_step = 1000000
test_step = 25000

target_update_step = int(run_step/100)
print_episode = 5
save_step = 10000

epsilon_init = 1.0
epsilon_min = 0.1

# Parameters for Curiosity-driven Exploration
beta = 0.2
lamb = 1.0
eta = 0.01
extrinsic_coeff = 1.0
intrinsic_coeff = 0.01

# Parameters for DDPG
actor_lr = 3e-4
critic_lr = 3e-4
tau = 5e-4
mu = 0
theta = 1e-3
sigma = 2e-3

# Paremeters for SAC
epsilon = 1e-6
alpha_lr = 3e-4

# Environment Setting
# env_config = {'gridSize':3}
env_config = {}

device = torch.device("cuda:0" if torch.cuda.is_available() else "cpu")

# Environment Path
game = "Hopper"
env_name = "./env/" + game + "/Windows/" + game

# 모델 저장 및 불러오기 경로
date_time = datetime.datetime.now().strftime("%Y%m%d-%H-%M-%S")

save_path = "./saved_models/" + game + "/" + date_time
load_path = "./saved_models/" + game + "/20200805-18-52-50_SAC"
