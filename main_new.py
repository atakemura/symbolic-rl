 # import ipdb; ipdb.set_trace()
import matplotlib
import gym
import gym_vgdl
import numpy as np
import os
from gym import wrappers

import time
import random
import subprocess

# Q-learning
import itertools
import pandas as pd
import sys

import pickle

from lib import plotting, py_asp, helper, induction, abduction

import gym, gym_vgdl

LASFILE = "output.las"
BACKGROUND = "background.lp"
CLINGOFILE = "clingo.lp"
LAS_CACHE = "cache.las"
LAS_CACHE_PATH = "log"

base_dir = os.path.dirname(os.path.abspath(__file__))
dir = os.path.join(base_dir, LAS_CACHE_PATH)
CACHE = os.path.join(dir, LAS_CACHE)

# Increase this to make the decay faster
DECAY_PARAM = 1

# TIME_RANGE = TIME_RANGE2 = 20
# env = gym.make('vgdl_aaa_small-v0')

# TIME_RANGE = 450
# TIME_RANGE2 = 30
# env = gym.make('vgdl_aaa_maze-v0')

TIME_RANGE = 300
TIME_RANGE2 = 20
# env = gym.make('vgdl_aaa_L_shape-v0')
env = gym.make('vgdl_aaa_small-v0')

HEIGHT = env.unwrapped.game.height
WIDTH = env.unwrapped.game.width

# TEMP_X = 5
# TEMP_Y = 1

def k_learning(env, num_episodes, epsilon=0.65, record_prefix=None, is_link=False):
    log_dir = None
    # Log everything and keep it here
    if record_prefix:
        log_dir = os.path.join(base_dir, "log")
        log_dir = helper.gen_log_dir(log_dir, record_prefix)
        print("log_dir ", log_dir)

    # check whether las file is in use
    is_las = False
    # check if 
    first_abduction = False

    is_start = True

    # Clean up all the files first
    helper.silentremove(LASFILE)
    helper.silentremove(BACKGROUND)
    helper.silentremove(CLINGOFILE)
    helper.silentremove(LAS_CACHE, LAS_CACHE_PATH)

    helper.create_file(LAS_CACHE, LAS_CACHE_PATH)
    # Add mode bias and adjacent definition for ILASP
    induction.copy_las_base(LASFILE, HEIGHT, WIDTH, is_link)

    wall_list = induction.get_all_walls(env)
    # import ipdb; ipdb.set_trace()
    stats = plotting.EpisodeStats(
        episode_lengths=np.zeros(num_episodes),
        episode_rewards=np.zeros(num_episodes))

    i_episode = 0
    while i_episode < num_episodes:
        # Decaying epsilon greedy params
        # epsilon = epsilon*(1/(i_episode+1)**DECAY_PARAM)
        # print("epsilon ", epsilon)

        # Reset the env and pick the first action
        print("==============NEW EPISODE======================")
        # TODO DO I want to update this in every episode??
        if is_start:
            state = env.reset()
            print("reset the starting position to the beginning")  
        

        agent_position = env.unwrapped.observer.get_observation()
        agent_position = agent_position["position"]
        # agent_position = env.unwrapped.game.getFeatures()
        print("agent_position ", agent_position)
        x = int(state[0])
        y = int(state[1])
        
        previous_state = state
        previous_state_at = py_asp.state_at(state[0], state[1], 1)
        any_exclusion = False
        is_exclusion = False

        # Once the plan is obtained, execute the plan
        if is_las:
            if first_abduction == False:
                # Run ILASP to get H
                hypothesis = induction.run_ILASP(LASFILE, CACHE)
                if record_prefix:
                    inputfile = os.path.join(base_dir, LASFILE)
                    helper.log_las(inputfile, hypothesis, log_dir, i_episode)
                
                abduction.make_lp(hypothesis, LASFILE, BACKGROUND, CLINGOFILE, agent_position, goal_state, TIME_RANGE2, WIDTH, HEIGHT)
                first_abduction = True
            
            print("agent_position ", agent_position)
            abduction.update_agent_position(agent_position, CLINGOFILE)

            answer_sets = abduction.run_clingo(CLINGOFILE)
            if record_prefix:
                inputfile = os.path.join(base_dir, CLINGOFILE)

                helper.log_asp(inputfile, answer_sets, log_dir, i_episode)

            states_plan, actions_array = abduction.sort_planning(answer_sets)
            print("ASP states ", states_plan)
            print("ASP actions ", actions_array)
            # Execute the planning
            for action_index, action in enumerate(actions_array):
                print("------------------------------")
                print("Planning phase... ", "take action ", action[1])

                # Flip a coin
                threshold = random.uniform(0,1)                

                # if threshold is less than epsilon, explore randomly a little bit
                if threshold < epsilon:
                    print("Taking a pure random action")
                    action_int = env.action_space.sample()
                    print("action_int ", action_int)
                    action_string = helper.convert_action(action_int)
                    print("random action is ", action_string)
                    next_state, reward, done, _ = env.step(action_int)
                                                         
                    x = int(next_state[0])
                    y = int(next_state[1])

                    if done:
                        reward = 100
                        i_episode += 1
                        break
                    else:
                        reward = -1
                    
                    observed_state = py_asp.state_at(next_state[0], next_state[1], action_index+2)
                    print("observed_state in random ",observed_state)
                
                    # Update stats
                    stats.episode_rewards[i_episode] += reward
                    stats.episode_lengths[i_episode] = action_index

                    new_wall_added = abduction.add_new_walls(previous_state, wall_list, CLINGOFILE)
                    if new_wall_added:
                        print("new walls added!")
                
                    # Add pos 
                    walls = induction.get_seen_walls(CLINGOFILE)
                    walls = walls + wall_list
                    any_exclusion, pos = induction.generate_plan_pos(previous_state_at, observed_state, states_plan, action_string, walls, is_link)
                    pos += "\n"
                    helper.append_to_file(pos, LASFILE)

                    if any_exclusion:
                        is_exclusion = True

                    is_start = False

                    state = next_state
                    previous_state = next_state
                    previous_state_at = observed_state
                    print("next_state ", next_state)
                    
                    if done:
                        is_start = True
                        i_episode += 1
                        break

                    break
                else:
                    action_int = helper.get_action(action[1])
                
                    next_state, reward, done, _ = env.step(action_int)
                    
                    is_start = False

                    x = int(next_state[0])
                    y = int(next_state[1])
                    if done:                 
                        reward = 100
                    else:
                        reward = -1

                    observed_state = py_asp.state_at(next_state[0], next_state[1], action_index+2)
                    print("observed_state ",observed_state)
                
                    # Update stats
                    stats.episode_rewards[i_episode] += reward
                    stats.episode_lengths[i_episode] = action_index

                    new_wall_added = abduction.add_new_walls(previous_state, wall_list, CLINGOFILE)
                    if new_wall_added:
                        print("new walls added!")
                
                    # Add pos 
                    walls = induction.get_seen_walls(CLINGOFILE)
                    walls = walls + wall_list
                    any_exclusion, pos = induction.generate_plan_pos(previous_state_at, observed_state, states_plan, action[1], walls, is_link)
                    pos += "\n"
                    helper.append_to_file(pos, LASFILE)
                    
                    if any_exclusion:
                        is_exclusion = True

                    # Check if the prediction is the same as observed state
                    predicted_state = abduction.get_predicted_state(previous_state_at, action[1], states_plan)
                    print("predicted_state ", predicted_state)
                    # if not, update H
                    if(predicted_state != observed_state):
                        print("H is probably not correct!")
            
                    state = next_state
                    previous_state = next_state
                    previous_state_at = observed_state

                    if done:
                        is_start = True
                        i_episode += 1
                        break

                env.render()
                time.sleep(0.1)  

            if is_exclusion:
                print("exclusion is there ", pos)
                hypothesis = induction.run_ILASP(LASFILE, CACHE)
                if record_prefix:
                    inputfile = os.path.join(base_dir, LASFILE)
                    helper.log_las(inputfile, hypothesis, log_dir, i_episode)

                print("New H ", hypothesis)
                abduction.update_h(hypothesis, CLINGOFILE)
            else:
                print("No exclusion!!")

        # Random action until ILASP kicks in
        else:
            # for t in itertools.count():
            for t in range(TIME_RANGE):
                
                env.render()
                # time.sleep(0.1)

                # Take a step
                action = env.action_space.sample()
                next_state, reward, done, _ = env.step(action)
                
                if done:
                    reward = 100
                    goal_state = next_state
                    is_las = True
                    break
                else:
                    reward -=1

                action_string = helper.convert_action(action)

                # Make ASP syntax of state transition
                induction.send_state_transition_pos(previous_state, next_state, action_string, wall_list, LASFILE, BACKGROUND)
                # Meanwhile, accumulate all background knowlege
                abduction.add_new_walls(previous_state, wall_list, BACKGROUND)
                # induction.add_surrounding_walls((previous_state, wall_list, BACKGROUND))
                previous_state = next_state

                # Update stats
                stats.episode_rewards[i_episode] += reward
                stats.episode_lengths[i_episode] = t

                if done:
                    break

                state = next_state
        
        if x == int(goal_state[0]) and y == int(goal_state[1]):
            is_start = True
            break

    return stats

# epsilon 0 means no exploration

# stats = k_learning(env, 10, epsilon=0, record_prefix="Field", is_link=False)

stats = k_learning(env, 10, epsilon=0.2, record_prefix=None, is_link=True)
# plotting.plot_episode_stats(stats)
plotting.plot_episode_stats_simple(stats)

# picklepath = base_dir + "/stats.pkl"
# print("picklepath ", picklepath)
# output = open(picklepath, "wb")
# pickle.dump(stats, output)
# output.close()