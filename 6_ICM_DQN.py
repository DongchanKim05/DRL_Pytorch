# Import Libraries
import numpy as np
import random
import time
import datetime
import os
from collections import deque
from mlagents.envs import UnityEnvironment

import torch
import torch.optim as optim

import agent
import model
import config

# Main function
if __name__ == '__main__':
    # set unity environment path (file_name)
    env = UnityEnvironment(file_name=config.env_name)
    # env = UnityEnvironment(file_name=config.env_name, worker_id=np.random.randint(100000))

    # setting brain for unity
    default_brain = env.brain_names[0]
    brain = env.brains[default_brain]

    train_mode = config.train_mode

    device = config.device

    model_ = model.DQN(config.action_size, "main").to(device)
    target_model_ = model.DQN(config.action_size, "target").to(device)

    model_ICM = model.ICM(config.action_size, "ICM").to(device)
    models = [model_, model_ICM]

    optimizer = optim.Adam(list(models[0].parameters()) + list(models[1].parameters()), lr=config.learning_rate)
    algorithm = "_ICM"
    agent = agent.DQNAgent(models, target_model_, optimizer, device, algorithm)

    step = 0
    episode = 0
    reward_list = []
    loss_list = []
    max_Q_list = []
    r_i_list = []
    loss_rl_list = []
    loss_fm_list = []
    loss_im_list = []

    # Reset Unity environment and set the train mode according to the environment setting (env_config)
    env_info = env.reset(train_mode=train_mode, config=config.env_config)[default_brain]

    # Game loop
    while step < config.run_step + config.test_step:
        # Initialize state, episode_rewards, done
        obs = 255 * np.array(env_info.visual_observations[0])
        obs = np.transpose(obs, (0, 3, 1, 2))
        episode_rewards = 0
        done = False

        for i in range(config.skip_frame*config.stack_frame):
            agent.obs_set.append(obs)

        state = agent.skip_stack_frame(obs)

        # loop for an episode
        while not done:
            if step == config.run_step:
                train_mode = False
                env_info = env.reset(train_mode=train_mode)[default_brain]

            # Decide action and apply the action to the Unity environment
            action = agent.get_action(state)
            env_info = env.step(action)[default_brain]

            # Get next state, reward, done information
            next_obs = 255 * np.array(env_info.visual_observations[0])
            next_obs = np.transpose(next_obs, (0, 3, 1, 2))
            reward = env_info.rewards[0]
            episode_rewards += reward
            done = env_info.local_done[0]

            next_state = agent.skip_stack_frame(next_obs)

            # Save data in replay memory while train mode
            if train_mode:
                agent.append_sample(state, action, reward, next_state, done)
            else:
                time.sleep(0.0)

            # Update state information
            state = next_state
            step += 1

            if step > config.start_train_step and train_mode:
                agent.epsilon = 0
                # 학습 수행
                loss, maxQ, r_i, loss_rl, loss_fm, loss_im = agent.train_model_ICM()
                loss_list.append(loss)
                max_Q_list.append(maxQ)
                r_i_list.append(r_i)
                loss_rl_list.append(loss_rl)
                loss_fm_list.append(loss_fm)
                loss_im_list.append(loss_im)

                # 타겟 네트워크 업데이트
                if step % (config.target_update_step) == 0:
                    agent.update_target()

            # 네트워크 모델 저장
            if step % config.save_step == 0 and step != 0 and train_mode:
                agent.save_model(config.load_model, train_mode)

        reward_list.append(episode_rewards)
        episode += 1

        # 게임 진행 상황 출력 및 텐서 보드에 보상과 손실함수 값 기록
        if episode % config.print_episode == 0 and episode != 0:
            print("step: {} / episode: {} / reward: {:.2f} / loss_tot: {:.4f} / loss_rl: {:.4f} / loss_fm: {:.6f} / loss_im: {:.4f} / maxQ: {:.2f} / reward_i: {:.6f}".format
                  (step, episode, np.mean(reward_list), np.mean(loss_list), config.lamb*np.mean(loss_rl_list),
                  config.beta*np.mean(loss_fm_list), (1-config.beta)*np.mean(loss_im_list), np.mean(max_Q_list), 100*np.mean(r_i_list)))
            # if train_mode:
            #     agent.write_scalar(np.mean(loss_list), np.mean(reward_list), np.mean(max_Q_list), episode)

            if train_mode:
                agent.write_scalar_ICM(np.mean(loss_list), np.mean(reward_list), np.mean(max_Q_list),
                np.mean(r_i_list), np.mean(loss_rl_list), np.mean(loss_fm_list), np.mean(loss_im_list), episode)

            reward_list = []
            loss_list = []
            max_Q_list = []
            r_i_list = []
            loss_rl_list = []
            loss_fm_list = []
            loss_im_list = []

    agent.save_model(config.load_model, train_mode)
    env.close()
