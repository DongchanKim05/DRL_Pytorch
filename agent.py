import model
import config

import torch
import torch.optim as optim
import torch.nn.functional as F
from torch.utils.tensorboard import SummaryWriter
import torch.nn as nn
from torch.distributions import Normal

import numpy as np
import random
from collections import deque
import os

device = config.device

# DQNAgent 클래스 -> DQN 알고리즘을 위한 다양한 함수 정의
class DQNAgent():
    def __init__(self, model, target_model, optimizer, device, algorithm):
        # 클래스의 함수들을 위한 값 설정
        if algorithm == ("_RND" or "_ICM"):
            self.model = model[0]
            self.model_a = model[1]
        else:
            self.model = model

        self.target_model = target_model
        self.optimizer = optimizer

        self.device = device
        self.algorithm = algorithm

        self.memory = deque(maxlen=config.mem_maxlen)
        self.obs_set = deque(maxlen=config.skip_frame*config.stack_frame)

        self.epsilon = config.epsilon_init

        if not config.load_model and config.train_mode:
            self.writer = SummaryWriter('{}'.format(config.save_path + self.algorithm))
        elif config.load_model and config.train_mode:
            self.writer = SummaryWriter('{}'.format(config.load_path))

        self.update_target()

        if config.load_model == True:
            try:
                self.model_a

            except:
                self.model.load_state_dict(torch.load(config.load_path+'/model.pth'), map_location=self.device)
                self.model.to(self.deivce)
                if config.train_mode: # train mode
                    self.model.train()
                else: # evaluation mode
                    self.model.eval()
            else:
                checkpoint = torch.load(config.load_path+'/model.pth', map_location=self.device)
                self.model.load_state_dict(checkpoint['model'])
                self.model_a.load_state_dict(checkpoint['model_a'])
                self.model.to(self.device)
                self.model_a.to(self.device)
                if config.train_mode: # train mode
                    self.model.train()
                    self.model_a.train()
                else: # evaluation mode
                    self.model.eval()
                    self.model_a.eval()

            # # 모델의 state_dict 출력
            # print("Model's state_dict:")
            # for param_tensor in self.model.state_dict():
            #     print(param_tensor, "\t", self.model.state_dict()[param_tensor].size())
            # print("----- and -----")
            # for param_tensor in self.model_a.state_dict():
            #     print(param_tensor, "\t", self.model_a.state_dict()[param_tensor].size())

            print("Model is loaded from {}".format(config.load_path+'/model.pth'))

    # Epsilon greedy 기법에 따라 행동 결정
    def get_action(self, state):
        if config.train_mode:
            if self.epsilon > np.random.rand():
                # 랜덤하게 행동 결정
                return np.random.randint(0, config.action_size)
            else:
                with torch.no_grad():
                # 네트워크 연산에 따라 행동 결정
                    Q = self.model(torch.from_numpy(state).unsqueeze(0).to(self.device))
                    return np.argmax(Q.cpu().detach().numpy())
        else:
            with torch.no_grad():
            # 네트워크 연산에 따라 행동 결정
                Q = self.model(torch.from_numpy(state).unsqueeze(0).to(self.device))
                return np.argmax(Q.cpu().detach().numpy())

    # 프레임을 skip하면서 설정에 맞게 stack
    def skip_stack_frame(self, obs):
        self.obs_set.append(obs)

        state = np.zeros([config.state_size[2]*config.stack_frame, config.state_size[0], config.state_size[1]])

        # skip frame마다 한번씩 obs를 stacking
        for i in range(config.stack_frame):
            state[config.state_size[2]*i : config.state_size[2]*(i+1), :,:] = self.obs_set[-1 - (config.skip_frame*i)]

        return np.uint8(state)

    # 리플레이 메모리에 데이터 추가 (상태, 행동, 보상, 다음 상태, 게임 종료 여부)
    def append_sample(self, state, action, reward, next_state, done):
        self.memory.append((state, action, reward, next_state, done))

    # 네트워크 모델 저장
    def save_model(self, load_model, train_mode):
        if not load_model and train_mode: # first training
            os.makedirs(config.save_path + self.algorithm, exist_ok=True)
            try:
                self.model_a
            except:
                torch.save(self.model.state_dict(), config.save_path + self.algorithm +'/model.pth')
            else:
                torch.save({
                    'model': self.model.state_dict(),
                    'model_a': self.model_a.state_dict()
                }, config.save_path + self.algorithm +'/model.pth')

            print("Save Model: {}".format(config.save_path + self.algorithm))

        elif load_model and train_mode: # additional training
            try:
                self.model_a
            except:
                torch.save(self.model.state_dict(), config.load_path +'/model.pth')
            else:
                torch.save({
                    'model': self.model.state_dict(),
                    'model_a': self.model_a.state_dict()
                }, config.load_path +'/model.pth')

            print("Save Model: {}".format(config.load_path))

    # 학습 수행
    def train_model(self):
        # 학습을 위한 미니 배치 데이터 샘플링
        mini_batch = random.sample(self.memory, config.batch_size)

        state_batch = torch.cat([torch.tensor([mini_batch[i][0]]) for i in range(config.batch_size)]).float().to(self.device)
        action_batch = torch.cat([torch.tensor([mini_batch[i][1]]) for i in range(config.batch_size)]).float().to(self.device)
        reward_batch = torch.cat([torch.tensor([mini_batch[i][2]]) for i in range(config.batch_size)]).float().to(self.device)
        next_state_batch = torch.cat([torch.tensor([mini_batch[i][3]]) for i in range(config.batch_size)]).float().to(self.device)
        done_batch = torch.cat([torch.tensor([mini_batch[i][4]]) for i in range(config.batch_size)]).float().to(self.device)

        # 타겟값 계산
        Q = self.model(state_batch)
        action_batch_onehot = torch.eye(config.action_size)[action_batch.type(torch.long)].to(self.device)
        acted_Q = torch.sum(Q * action_batch_onehot, axis=-1).unsqueeze(1)

        with torch.no_grad():
            target_next_Q = self.target_model(next_state_batch)
            max_next_Q = torch.max(target_next_Q, dim=1, keepdim=True).values
            target_Q = (1. - done_batch).view(config.batch_size, -1) * config.discount_factor * max_next_Q + reward_batch.view(config.batch_size, -1)

        max_Q = torch.mean(torch.max(target_Q, axis=0).values).cpu().numpy()

        loss = F.smooth_l1_loss(acted_Q, target_Q)
        self.optimizer.zero_grad()
        loss.backward()
        self.optimizer.step()

        return loss.item(), max_Q

    # 타겟 네트워크 업데이트
    def update_target(self):
        self.target_model.load_state_dict(self.model.state_dict())

    def write_scalar(self, loss, reward, maxQ, episode):
        self.writer.add_scalar('Mean_Loss', loss, episode)
        self.writer.add_scalar('Mean_Reward', reward, episode)
        self.writer.add_scalar('Max_Q', maxQ, episode)

    def write_scalar_ICM(self, loss, reward, maxQ, r_i, episode, loss_rl, loss_fm, loss_im):
        self.writer.add_scalar('Mean_Loss', loss, episode)
        self.writer.add_scalar('Mean_Reward', reward, episode)
        self.writer.add_scalar('Max_Q', maxQ, episode)
        self.writer.add_scalar('intrinsic_Reward', r_i, episode)
        self.writer.add_scalar('Mean_Loss_Rl', loss_rl, episode)
        self.writer.add_scalar('Mean_Loss_Fm', loss_fm, episode)
        self.writer.add_scalar('Mean_Loss_Im', loss_im, episode)

    # Epsilon greedy 기법에 따라 행동 결정
    def get_action_noisy(self, state, step, train_mode):
        if step < config.start_train_step and train_mode:
            # 랜덤하게 행동 결정
            return np.random.randint(0, config.action_size)
        else:
            # 네트워크 연산에 따라 행동 결정
            Q = self.model(torch.from_numpy(state).unsqueeze(0).to(self.device), torch.tensor(train_mode).to(self.device))
            return np.argmax(Q.cpu().detach().numpy())

    # 학습 수행
    def train_model_double(self):
        # 학습을 위한 미니 배치 데이터 샘플링
        mini_batch = random.sample(self.memory, config.batch_size)

        state_batch = []
        action_batch = []
        reward_batch = []
        next_state_batch = []
        done_batch = []

        for i in range(config.batch_size):
            state_batch.append(mini_batch[i][0])
            action_batch.append(mini_batch[i][1])
            reward_batch.append(mini_batch[i][2])
            next_state_batch.append(mini_batch[i][3])
            done_batch.append(mini_batch[i][4])

        # 타겟값 계산
        predict_Q = self.model(torch.FloatTensor(state_batch).to(self.device))
        target_Q = predict_Q.cpu().detach().numpy()
        target_nextQ = self.target_model(torch.FloatTensor(next_state_batch).to(self.device)).cpu().detach().numpy()

        Q_a = self.model(torch.FloatTensor(next_state_batch).to(self.device)).cpu().detach().numpy()
        max_Q = np.max(target_Q)

        with torch.no_grad():
            for i in range(config.batch_size):
                if done_batch[i]:
                    target_Q[i, action_batch[i]] = reward_batch[i]
                else:
                    action_ind = np.argmax(Q_a[i])
                    target_Q[i, action_batch[i]] = reward_batch[i] + config.discount_factor * target_nextQ[i][action_ind]

        loss = F.smooth_l1_loss(predict_Q.to(self.device), torch.from_numpy(target_Q).to(self.device))
        self.optimizer.zero_grad()
        loss.backward()
        self.optimizer.step()

        return loss.item(), max_Q

    def train_model_noisy(self):
        # 학습을 위한 미니 배치 데이터 샘플링
        mini_batch = random.sample(self.memory, config.batch_size)
        state_batch = torch.cat([torch.tensor([mini_batch[i][0]]) for i in range(config.batch_size)]).float().to(self.device)
        action_batch = torch.cat([torch.tensor([mini_batch[i][1]]) for i in range(config.batch_size)]).float().to(self.device)
        reward_batch = torch.cat([torch.tensor([mini_batch[i][2]]) for i in range(config.batch_size)]).float().to(self.device)
        next_state_batch = torch.cat([torch.tensor([mini_batch[i][3]]) for i in range(config.batch_size)]).float().to(self.device)
        done_batch = torch.cat([torch.tensor([mini_batch[i][4]]) for i in range(config.batch_size)]).float().to(self.device)

        # 타겟값 계산
        Q = self.model(state_batch, train=True)
        action_batch_onehot = torch.eye(config.action_size)[action_batch.type(torch.long)].to(self.device)
        acted_Q = torch.sum(Q * action_batch_onehot, axis=-1).unsqueeze(1)

        with torch.no_grad():
            target_next_Q = self.target_model(next_state_batch, train=False)
            max_next_Q = torch.max(target_next_Q, dim=1, keepdim=True).values
            target_Q = (1. - done_batch).view(config.batch_size, -1) * config.discount_factor * max_next_Q + reward_batch.view(config.batch_size, -1)

        max_Q = torch.mean(torch.max(target_Q, axis=0).values).cpu().numpy()

        loss = F.smooth_l1_loss(acted_Q, target_Q)
        self.optimizer.zero_grad()
        loss.backward()
        self.optimizer.step()

        return loss.item(), max_Q

    # 학습 수행
    def train_model_ICM(self):
        # 학습을 위한 미니 배치 데이터 샘플링
        mini_batch = random.sample(self.memory, config.batch_size)

        state_batch = torch.cat([torch.tensor([mini_batch[i][0]]) for i in range(config.batch_size)]).float().to(self.device)
        action_batch = torch.cat([torch.tensor([mini_batch[i][1]]) for i in range(config.batch_size)]).float().to(self.device)
        reward_batch = torch.cat([torch.tensor([mini_batch[i][2]]) for i in range(config.batch_size)]).float().to(self.device)
        next_state_batch = torch.cat([torch.tensor([mini_batch[i][3]]) for i in range(config.batch_size)]).float().to(self.device)
        done_batch = torch.cat([torch.tensor([mini_batch[i][4]]) for i in range(config.batch_size)]).float().to(self.device)

        # ICM
        x_next_encode, x_fm, x_im = self.model_a(state_batch, next_state_batch, action_batch)

        # calculate intrinsic reward
        reward_i = (config.eta * 0.5) * torch.sum(torch.square(x_fm - x_next_encode), dim=1)

        Q = self.model(state_batch)
        action_batch_onehot = torch.eye(config.action_size)[action_batch.type(torch.long)].to(self.device)
        acted_Q = torch.sum(Q * action_batch_onehot, axis=-1).unsqueeze(1)

        with torch.no_grad():
            for i in range(config.batch_size):
                reward_batch[i] = (config.extrinsic_coeff * reward_batch[i]) + (config.intrinsic_coeff * reward_i[i])

            target_next_Q = self.target_model(next_state_batch)
            max_next_Q = torch.max(target_next_Q, dim=1, keepdim=True).values
            target_Q = (1. - done_batch).view(config.batch_size, -1) * config.discount_factor * max_next_Q + reward_batch.view(config.batch_size, -1)

        max_Q = torch.mean(torch.max(target_Q, axis=0).values).cpu().numpy()

        loss_rl = F.smooth_l1_loss(acted_Q, target_Q)
        # ICM related losses
        loss_fm = F.mse_loss(input=x_fm.to(self.device), target=x_next_encode.to(self.device))
        loss_im = F.cross_entropy(input=x_im.to(self.device), target=action_batch.to(device=self.device, dtype=torch.int64))

        loss = (config.lamb * loss_rl) + (config.beta * loss_fm) + ((1-config.beta) * loss_im)

        self.optimizer.zero_grad()
        loss_rl.backward(retain_graph=True)
        loss_fm.backward(retain_graph=True)
        loss_im.backward(retain_graph=True)

        self.optimizer.step()

        return loss.item(), max_Q, config.intrinsic_coeff*reward_i.cpu().detach().numpy(), loss_rl.item(), loss_fm.item(), loss_im.item()

    # 학습 수행
    def train_model_RND(self):
        # 학습을 위한 미니 배치 데이터 샘플링
        mini_batch = random.sample(self.memory, config.batch_size)

        state_batch = torch.cat([torch.tensor([mini_batch[i][0]]) for i in range(config.batch_size)]).float().to(self.device)
        action_batch = torch.cat([torch.tensor([mini_batch[i][1]]) for i in range(config.batch_size)]).float().to(self.device)
        reward_batch = torch.cat([torch.tensor([mini_batch[i][2]]) for i in range(config.batch_size)]).float().to(self.device)
        next_state_batch = torch.cat([torch.tensor([mini_batch[i][3]]) for i in range(config.batch_size)]).float().to(self.device)
        done_batch = torch.cat([torch.tensor([mini_batch[i][4]]) for i in range(config.batch_size)]).float().to(self.device)

        # RND
        x_next_encode, x_next_encode_t = self.model_a(next_state_batch)

        # calculate intrinsic reward
        reward_i = (config.eta * 0.5) * torch.sum(torch.square(x_next_encode - x_next_encode_t), dim=1)

        Q = self.model(state_batch)
        # print(f"Q: {Q}")
        action_batch_onehot = torch.eye(config.action_size)[action_batch.type(torch.long)].to(self.device)
        acted_Q = torch.sum(Q * action_batch_onehot, axis=-1).unsqueeze(1)

        with torch.no_grad():
            for i in range(config.batch_size):
                reward_batch[i] = (config.extrinsic_coeff * reward_batch[i]) + (config.intrinsic_coeff * reward_i[i])

            target_next_Q = self.target_model(next_state_batch)
            max_next_Q = torch.max(target_next_Q, dim=1, keepdim=True).values
            target_Q = (1. - done_batch).view(config.batch_size, -1) * config.discount_factor * max_next_Q + reward_batch.view(config.batch_size, -1)

        max_Q = torch.mean(torch.max(target_Q, axis=0).values).cpu().numpy()

        loss_rl = F.smooth_l1_loss(acted_Q, target_Q)

        # RND loss
        loss_fm = F.mse_loss(input=x_next_encode.to(self.device), target=x_next_encode_t.to(self.device))

        loss = (config.lamb * loss_rl) + (config.beta * loss_fm)

        self.optimizer.zero_grad()
        loss_rl.backward(retain_graph=True)
        loss_fm.backward(retain_graph=True)
        self.optimizer.step()

        return loss.item(), max_Q, config.intrinsic_coeff*reward_i.cpu().detach().numpy(), loss_rl.item(), loss_fm.item()

# OU Noise 클래스 -> DDPG 에서 action 을 결정할 때 사용
class OUNoise():
    def __init__(self):
        self.X = np.zeros(config.action_size)
        self.mu = config.mu
        self.theta = config.theta
        self.sigma = config.sigma

    def sample(self):
        dx = self.theta * (self.mu - self.X) + self.sigma * np.random.randn(len(self.X))
        self.X += dx
        return self.X

# DDPGAgent 클래스 -> DDPG 알고리즘을 위한 다양한 함수 정의
class DDPGAgent():
    def __init__(self, actor, critic, target_actor, target_critic, optimizer_actor, optimizer_critic, device, algorithm):
        # 클래스의 함수들을 위한 값 설정
        self.actor = actor
        self.critic = critic
        self.target_actor = target_actor
        self.target_critic = target_critic

        self.ou_noise = OUNoise()

        self.optimizer_actor = optimizer_actor
        self.optimizer_critic = optimizer_critic

        self.device = device
        self.algorithm = algorithm

        self.memory = deque(maxlen=config.mem_maxlen)
        self.obs_set = deque(maxlen=config.skip_frame*config.stack_frame)

        self.epsilon = config.epsilon_init

        if not config.load_model and config.train_mode:
            self.writer = SummaryWriter('{}'.format(config.save_path + self.algorithm))
        elif config.load_model and config.train_mode:
            self.writer = SummaryWriter('{}'.format(config.load_path))

        if config.load_model == True:
            checkpoint = torch.load(config.load_path+'/model.pth', map_location=self.device)
            self.critic.load_state_dict(checkpoint['critic'])
            self.actor.load_state_dict(checkpoint['actor'])
            self.critic.to(self.device)
            self.actor.to(self.device)
            if config.train_mode: # train mode
                self.critic.train()
                self.actor.train()
            else: # evaluation mode
                self.critic.eval()
                self.actor.eval()

            print("Model is loaded from {}".format(config.load_path+'/model.pth'))

    # 네트워크 연산 + OU noise (training 시) 에 따라 행동 결정
    def get_action(self, state, train_mode):
        with torch.no_grad():
            policy = self.actor(torch.from_numpy(state).unsqueeze(0).to(self.device))
            action = policy.cpu().detach().numpy()
            noise = self.ou_noise.sample()
            return action + noise if train_mode else action

    # 리플레이 메모리에 데이터 추가 (상태, 행동, 보상, 다음 상태, 게임 종료 여부)
    def append_sample(self, state, action, reward, next_state, done):
        self.memory.append((state, action, reward, next_state, done))

    # 네트워크 모델 저장
    def save_model(self, load_model, train_mode):
        if not load_model and train_mode: # first training
            os.makedirs(config.save_path + self.algorithm, exist_ok=True)
            torch.save({
                'critic': self.critic.state_dict(),
                'actor': self.actor.state_dict()
            }, config.save_path + self.algorithm +'/model.pth')

            print("Save Model: {}".format(config.save_path + self.algorithm))

        elif load_model and train_mode: # additional training
            torch.save({
                'critic': self.critic.state_dict(),
                'actor': self.actor.state_dict()
            }, config.load_path +'/model.pth')

            print("Save Model: {}".format(config.load_path))

    # 학습 수행
    def train_model(self):
        self.actor.train(), self.critic.train()
        self.target_actor.train(), self.target_critic.train()

        # 학습을 위한 미니 배치 데이터 샘플링
        mini_batch = random.sample(self.memory, config.batch_size)

        state_batch = torch.cat([torch.tensor([mini_batch[i][0]]) for i in range(config.batch_size)]).float().to(self.device)
        action_batch = torch.cat([torch.tensor([mini_batch[i][1]]) for i in range(config.batch_size)]).float().to(self.device)
        reward_batch = torch.cat([torch.tensor([mini_batch[i][2]]) for i in range(config.batch_size)]).float().to(self.device)
        next_state_batch = torch.cat([torch.tensor([mini_batch[i][3]]) for i in range(config.batch_size)]).float().to(self.device)
        done_batch = torch.cat([torch.tensor([mini_batch[i][4]]) for i in range(config.batch_size)]).float().to(self.device)

        # get target
        Q = self.critic(state_batch, action_batch)

        with torch.no_grad():
            target_next_policy = self.target_actor(next_state_batch)
            target_next_Q = self.target_critic(next_state_batch, target_next_policy)
            max_next_Q = torch.max(target_next_Q, dim=1, keepdim=True).values
            target_Q = (1. - done_batch).view(config.batch_size, -1) * config.discount_factor * max_next_Q + reward_batch.view(config.batch_size, -1)
        max_Q = torch.mean(torch.max(target_Q, axis=0).values).cpu().numpy()

        # update critic
        critic_loss = F.mse_loss(input=Q, target=target_Q)
        self.optimizer_critic.zero_grad()
        critic_loss.backward()
        self.optimizer_critic.step()

        # update actor
        policy = self.actor(state_batch)

        actor_loss = -self.critic(state_batch, policy).mean()
        self.optimizer_actor.zero_grad()
        actor_loss.backward()
        self.optimizer_actor.step()

        return critic_loss.item(), actor_loss.item(), max_Q

    # 타겟 네트워크 업데이트 : hard update
    def hard_update_target(self):
        self.target_actor.load_state_dict(self.actor.state_dict())
        self.target_critic.load_state_dict(self.critic.state_dict())

    # 타겟 네트워크 업데이트 : soft update
    def soft_update_target(self):
        self.soft_update(self.actor, self.target_actor, config.tau)
        self.soft_update(self.critic, self.target_critic, config.tau)

    def soft_update(self, model, target_model, tau):
        for target_param, param in zip(target_model.parameters(), model.parameters()):
            target_param.data.copy_(tau*param.data + (1-tau)*target_param.data)

    def write_scalar(self, loss_critic, loss_actor, reward, maxQ, episode):
        self.writer.add_scalar('Mean_Loss_Critic', loss_critic, episode)
        self.writer.add_scalar('Mean_Loss_Actor', loss_actor, episode)
        self.writer.add_scalar('Mean_Reward', reward, episode)
        self.writer.add_scalar('Max_Q', maxQ, episode)

# SACAgent 클래스 -> SAC 알고리즘을 위한 다양한 함수 정의
class SACAgent():
    def __init__(self, actor, critic, target_critic, optimizer_actor, optimizer_critic, optimizer_alpha, alpha, log_alpha, target_entropy, device, algorithm):
        # 클래스의 함수들을 위한 값 설정
        self.actor = actor
        self.critic = critic
        self.target_critic = target_critic

        self.optimizer_actor = optimizer_actor
        self.optimizer_critic = optimizer_critic
        self.optimizer_alpha = optimizer_alpha

        self.device = device
        self.algorithm = algorithm

        self.memory = deque(maxlen=config.mem_maxlen)
        self.obs_set = deque(maxlen=config.skip_frame*config.stack_frame)

        self.epsilon = config.epsilon_init
        self.alpha = alpha
        self.log_alpha = log_alpha
        self.target_entropy = target_entropy

        if not config.load_model and config.train_mode:
            self.writer = SummaryWriter('{}'.format(config.save_path + self.algorithm))
        elif config.load_model and config.train_mode:
            self.writer = SummaryWriter('{}'.format(config.load_path))

        if config.load_model == True:
            checkpoint = torch.load(config.load_path+'/model.pth', map_location=self.device)
            self.critic.load_state_dict(checkpoint['critic'])
            self.actor.load_state_dict(checkpoint['actor'])
            self.critic.to(self.device)
            self.actor.to(self.device)
            if config.train_mode: # train mode
                self.critic.train()
                self.actor.train()
            else: # evaluation mode
                self.critic.eval()
                self.actor.eval()

            print("Model is loaded from {}".format(config.load_path+'/model.pth'))

    # reparameterization trick 에 따라 행동 결정
    def get_action(self, state, train_mode):
        mu, std = self.actor(torch.from_numpy(state).unsqueeze(0).to(self.device))
        if not train_mode:
            std = 0
        m = Normal(mu, std)
        z = m.rsample()
        action = torch.tanh(z)
        action = action.data.cpu().detach().numpy()
        return action

    def sample_action(self, mu, std):
        m = Normal(mu, std)
        z = m.rsample()
        action = torch.tanh(z)
        log_prob = m.log_prob(z)
        # Enforcing Action Bounds
        log_prob -= torch.log(1 - action.pow(2) + config.epsilon)
        log_prob = log_prob.sum(1, keepdim=True)
        return action, log_prob


    # 리플레이 메모리에 데이터 추가 (상태, 행동, 보상, 다음 상태, 게임 종료 여부)
    def append_sample(self, state, action, reward, next_state, done):
        self.memory.append((state, action, reward, next_state, done))

    # 네트워크 모델 저장
    def save_model(self, load_model, train_mode):
        if not load_model and train_mode: # first training
            os.makedirs(config.save_path + self.algorithm, exist_ok=True)
            torch.save({
                'critic': self.critic.state_dict(),
                'actor': self.actor.state_dict()
            }, config.save_path + self.algorithm +'/model.pth')

            print("Save Model: {}".format(config.save_path + self.algorithm))

        elif load_model and train_mode: # additional training
            torch.save({
                'critic': self.critic.state_dict(),
                'actor': self.actor.state_dict()
            }, config.load_path +'/model.pth')

            print("Save Model: {}".format(config.load_path))

    # 학습 수행
    def train_model(self):
        self.actor.train(), self.critic.train()
        self.target_critic.train()

        # 학습을 위한 미니 배치 데이터 샘플링
        mini_batch = random.sample(self.memory, config.batch_size)

        state_batch = torch.cat([torch.tensor([mini_batch[i][0]]) for i in range(config.batch_size)]).float().to(self.device)
        action_batch = torch.cat([torch.tensor([mini_batch[i][1]]) for i in range(config.batch_size)]).float().to(self.device)
        reward_batch = torch.cat([torch.tensor([mini_batch[i][2]]) for i in range(config.batch_size)]).float().to(self.device)
        next_state_batch = torch.cat([torch.tensor([mini_batch[i][3]]) for i in range(config.batch_size)]).float().to(self.device)
        done_batch = torch.cat([torch.tensor([mini_batch[i][4]]) for i in range(config.batch_size)]).float().to(self.device)

        # get Q values (Q1, Q2)
        Q1, Q2 = self.critic(state_batch, action_batch)

        with torch.no_grad():
            mu, std = self.actor(next_state_batch)
            action_next, log_prob_next = self.sample_action(mu, std)
            target_next_Q1, target_next_Q2 = self.target_critic(next_state_batch, action_next)
            min_target_next_Q = torch.min(target_next_Q1, target_next_Q2) - self.alpha * log_prob_next
            target_Q = (1. - done_batch).view(config.batch_size, -1) * config.discount_factor * min_target_next_Q + reward_batch.view(config.batch_size, -1)

        max_Q = torch.mean(torch.max(target_Q, axis=0).values).cpu().numpy()

        # update critic
        critic_loss1 = F.mse_loss(input=Q1, target=target_Q.detach())
        critic_loss2 = F.mse_loss(input=Q2, target=target_Q.detach())
        critic_loss = critic_loss1 + critic_loss2

        self.optimizer_critic.zero_grad()
        critic_loss.backward()
        self.optimizer_critic.step()

        # update actor
        mu, std = self.actor(state_batch)
        action, log_prob = self.sample_action(mu, std)

        Q1, Q2 = self.critic(state_batch, action)
        min_Q = torch.min(Q1, Q2)

        actor_loss = ((self.alpha * log_prob) - min_Q).mean()
        self.optimizer_actor.zero_grad()
        actor_loss.backward(retain_graph=True)
        self.optimizer_actor.step()

        # update alpha
        alpha_loss = -(self.log_alpha * (log_prob + self.target_entropy).detach()).mean()
        self.optimizer_alpha.zero_grad()
        alpha_loss.backward()
        self.optimizer_alpha.step()

        self.alpha = self.log_alpha.exp()

        return critic_loss1.item(), critic_loss2.item(), actor_loss.item(), alpha_loss.item(), max_Q, self.alpha.cpu().detach().numpy()

    # 타겟 네트워크 업데이트 : hard update
    def hard_update_target(self):
        self.target_critic.load_state_dict(self.critic.state_dict())

    # 타겟 네트워크 업데이트 : soft update
    def soft_update_target(self):
        self.soft_update(self.critic, self.target_critic, config.tau)

    def soft_update(self, model, target_model, tau):
        for target_param, param in zip(target_model.parameters(), model.parameters()):
            target_param.data.copy_(tau*param.data + (1-tau)*target_param.data)

    def write_scalar(self, loss_critic1, loss_critic2, loss_actor, loss_alpha, reward, maxQ, alpha, episode):
        self.writer.add_scalar('Mean_Loss_Critic1', loss_critic1, episode)
        self.writer.add_scalar('Mean_Loss_Critic2', loss_critic2, episode)
        self.writer.add_scalar('Mean_Loss_Actor', loss_actor, episode)
        self.writer.add_scalar('Mean_Loss_Alpha', loss_alpha, episode)
        self.writer.add_scalar('Mean_Reward', reward, episode)
        self.writer.add_scalar('Max_Q', maxQ, episode)
        self.writer.add_scalar('Alpha', alpha, episode)
