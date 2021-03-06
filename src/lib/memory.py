import random
from collections import deque

import numpy as np

from .utils import to_tuple


class Memory:
    def __init__(self, observation_shape, observation_dtype=np.float,
                 action_shape=1, action_dtype=np.float,
                 state_stacksize=1, capacity=1e6):
        self._state_stacksize = state_stacksize
        self._capacity = int(capacity) + self._state_stacksize
        self._observation_shape = observation_shape
        state_store_shape = to_tuple(self._capacity, self._observation_shape)
        self._observations = np.zeros(state_store_shape,
                                      dtype=observation_dtype).squeeze()
        self._actions = np.zeros(to_tuple(self._capacity, action_shape),
                                 dtype=action_dtype).squeeze()
        self._rewards = np.zeros(self._capacity, dtype=np.float)
        self._terminals = np.zeros(self._capacity, dtype=np.bool)
        self._head = -1
        self._size = 0

    def __len__(self):
        return self._size

    def set_terminal(self, index, terminal):
        index = index % (self._head + 1)
        self._terminals[index] = terminal

    def __getitem__(self, indices):
        """Get a list of (s, a, r, t) tuples.

        NOTE: Each state in s contains the current state in s[:-1] and the
        next state in s[1:] for memory efficiency.
        """
        if not isinstance(indices, (list, tuple)):
            indices = (indices,)
        actions = self._actions[indices]
        rewards = self._rewards[indices]
        terminals = self._terminals[indices]
        states = self._get_states(indices)
        return list(zip(states, actions, rewards, terminals))

    def _get_states(self, indices):
        """Get states, each state being a stack of observations."""
        indices = np.array(to_tuple(indices))
        start = self._state_stacksize - 1
        denom = len(self) if len(self) else self._capacity
        states = np.stack([self._observations[(indices - i) % denom]
                           for i in range(start, -2, -1)],
                          axis=-1)
        # states = np.swapaxes(states, 0, 1)
        term_stacks = np.stack([self._terminals[(indices - i) % denom]
                                for i in range(start, -2, -1)],
                               axis=-1)
        for state, terms in zip(states, term_stacks):
            # Remove everything before a terminal obs if before the current.
            term = np.flatnonzero(terms[:-2])
            if len(term):
                term = np.max(term)
                state[..., :term + 1] = np.zeros_like(state[0])
            # Remove the next obs if the current is a terminal obs.
            if terms[-2] is True:
                state[..., -1] = np.zeros_like(state[0])
        return states

    def add(self, state, action, reward, terminal):
        """Add experience to memory buffer."""
        self._head = (self._head + 1) % self._capacity
        self._observations[self._head] = state
        self._actions[self._head] = action
        self._rewards[self._head] = reward
        self._terminals[self._head] = terminal
        if self._size < self._capacity:
            self._size += 1
        return self._head

    def now(self, observation):
        """Combine the last couple of observations with the new observation."""
        try:
            state = self._get_states(self._head)[0, ..., 1:]
        except ZeroDivisionError as e:
            if not len(self):
                shape = to_tuple(self._observation_shape,
                                 self._state_stacksize)
                state = np.zeros(shape, dtype=self._observations.dtype)
            else:
                raise e
        state[..., -1] = observation
        return np.squeeze(state)

    def sample(self, batchsize=32):
        """Sample a random batch from the memory buffer."""
        start = (self._head + self._state_stacksize) - len(self)
        indices = random.sample(range(start, self._head), batchsize)
        return self[indices]


class MultiMemory:
    def __init__(self, *memories):
        self._memories = list(memories)

    def __len__(self):
        return sum([len(memory) for memory in self._memories])

    def add(self, memory: Memory):
        self._memories.append(memory)

    def sample(self, batchsize=32):
        """Sample a batch of experiences uniformly from all memories."""
        batch = []
        memory_select = np.random.randint(0, len(self._memories), batchsize)
        _, counts = np.unique(memory_select, return_counts=True)
        for memory, n in zip(self._memories, counts):
            batch.extend(memory.sample(n))
        return batch
