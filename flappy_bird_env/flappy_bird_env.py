from typing import Any, Dict, List, SupportsFloat, Tuple
from gymnasium.core import ActType, ObsType, RenderFrame

import functools

import gymnasium as gym
import numpy as np
import pygame

from gymnasium.spaces import Box, Discrete

from .background import Background
from .base import Base
from .bird import Bird
from .pipe import Pipe


class FlappyBirdEnv(gym.Env):
    action_space = Discrete(2)
    """
    The Space object corresponding to valid actions, all valid actions should be
    contained with the space.
    """

    observation_space = Box(low=0, high=255, shape=(800, 576, 3),
                            dtype=np.uint8)
    """
    The Space object corresponding to valid observations, all valid observations
    should be contained with the space. It is static across all instances.
    """

    metadata = {"render_modes": ["human", "rgb_array"], "render_fps": 60}
    """
    The metadata of the environment containing rendering modes, rendering fps,
    etc.
    """

    def __init__(self, render_mode: str | None = None):
        self.render_mode = render_mode

        self._background = None
        self._pipes = None
        self._base = None
        self._bird = None
        self._old_distance = np.inf
        self._surface = None
        self._clock = None
        if self.render_mode == "human":
            self._clock = pygame.time.Clock()

        self._last_action = 0
        self._score = 0

    @property
    def observation(self) -> ObsType:
        pixels = pygame.surfarray.pixels3d(self._surface)
        return np.transpose(np.array(pixels), axes=(1, 0, 2))

    @property
    def reward(self) -> SupportsFloat:

        new_distance = self._calculate_distance()

        if self._is_pipe_passed():
            return 1
        elif self.terminated:
            self._old_distance = np.inf
            return -1
        elif new_distance <= self._old_distance:
            self._old_distance = new_distance
            return self._calculate_distance_reward()
        else:
            return 0

    @property
    def terminated(self) -> bool:
        return any([*[pipe.collide(self._bird) for pipe in self._pipes],
                    self._bird.y + self._bird.image.get_height() >= 730,
                    self._bird.y < 0])

    @property
    def truncated(self) -> bool:
        return False

    @property
    def info(self) -> Dict[str, Any]:
        return {
            "background": {
                "upper_left": (0, 0)
            },
            "pipes": [{
                "x": pipe.x,
                "height": pipe.height,
                "top": pipe.top,
                "bottom": pipe.bottom
            } for pipe in self._pipes],
            "base": {
                "x1": self._base.x1,
                "x2": self._base.x2,
                "y": self._base.y
            },
            "bird": {
                "x": self._bird.x,
                "y": self._bird.y
            },
            "last_action": self._last_action,
            "score": self._score
        }
    
    def _is_pipe_passed(self) -> bool:
        return any(not pipe.passed and pipe.x < self._bird.x for pipe in self._pipes)

    def _is_bird_out_of_bounds(self) -> bool:
        bird_x, bird_y = self._bird.x, self._bird.y
        top_line_point1, top_line_point2 = self._get_line_points('top')
        bottom_line_point1, bottom_line_point2 = self._get_line_points('bottom')

        above_top_line = self._is_point_above_line(bird_x, bird_y, top_line_point1, top_line_point2)
        above_bottom_line = self._is_point_above_line(bird_x, bird_y, bottom_line_point1, bottom_line_point2)

        return not above_top_line or above_bottom_line

    def _is_bird_in_pipe_but_off_center(self) -> bool:
        bird_x, bird_y = self._bird.x, self._bird.y
        pipe = self._pipes[0]
        gap_center_y = (pipe.bottom + pipe.height) / 2

        in_pipe = pipe.x - 64 < bird_x < pipe.x + 100
        off_center = not (gap_center_y - 40 < bird_y < gap_center_y + 40)

        return in_pipe and off_center

    def _calculate_distance(self) -> float:
        bird_y = self._bird.y
        bird_x = self._bird.x
        pipe = self._pipes[0]
        gap_center_y = (pipe.bottom + pipe.height) / 2
        euclidean_distance = np.sqrt((bird_y - gap_center_y) ** 2 + (bird_x - pipe.x+150) ** 2)
        return euclidean_distance

    def _calculate_distance_reward(self) -> float:
        bird_y = self._bird.y
        bird_x = self._bird.x
        pipe = self._pipes[0]
        gap_center_y = (pipe.bottom + pipe.height) / 2
        euclidean_distance = np.sqrt((bird_y - gap_center_y) ** 2 + (bird_x - pipe.x+150) ** 2)
        return (410 - euclidean_distance) / 410

    def _get_line_points(self, line_type: str):
        pipe = self._pipes[0]
        sky_y = 0
        ground_y = self._base.y
        gap_center_y = (pipe.bottom + pipe.height) / 2

        if line_type == 'top':
            return [pipe.x - 500, sky_y], [pipe.x - 50, gap_center_y - 20]
        elif line_type == 'bottom':
            return [pipe.x - 500, ground_y], [pipe.x - 50, gap_center_y + 20]
        else:
            raise ValueError("Invalid line type")


    def _is_point_above_line(self, point_x, point_y, line_point1, line_point2):
        """
        Check if a point is above or below the line defined by two points.
        
        :param point: Tuple (x, y) for the point to check.
        :param line_point1: Tuple (x, y) for the first point on the line.
        :param line_point2: Tuple (x, y) for the second point on the line.
        :return: True if the point is above the line, False if below.
        """
        # Calculate the slope (m)
        m = (line_point2[1] - line_point1[1]) / (line_point2[0] - line_point1[0])
        # Calculate the y-intercept (b)
        b = line_point1[1] - m * line_point1[0]
        
        # Calculate the y value of the line at the x position of the point
        y_line_at_point_x = m * point_x + b
        
        # If the y value of the point is greater than the line's y value, it's above the line
        return point_y > y_line_at_point_x

    def step(self, action: ActType) -> \
            tuple[ObsType, SupportsFloat, bool, bool, Dict[str, Any]]:
        """
        Run one timestep of the environment’s dynamics using the agent actions.

        When the end of an episode is reached (`terminated` or `truncated`), it
        is necessary to call `reset()` to reset this environment’s state for the
        next episode.

        Parameters:
        - action (ActType): an action provided by the agent to update the
        environment state.

        Returns:
        - observation (ObsType): An element of the environment’s
        `observation_space` as the next observation due to the agent actions.
        An example is a numpy array containing the positions and velocities of
        the pole in CartPole.

        - reward (SupportsFloat): The reward as a result of taking the action.

        - terminated (bool): Whether the agent reaches the terminal state (as
        defined under the MDP of the task) which can be positive or negative.
        An example is reaching the goal state or moving into the lava from the
        Sutton and Barton, Gridworld. If true, the user needs to call `reset()`.

        - truncated (bool): Whether the truncation condition outside the scope
        of the MDP is satisfied. Typically, this is a timelimit, but could also
        be used to indicate an agent physically going out of bounds. Can be used
        to end the episode prematurely before a terminal state is reached. If
        true, the user needs to call `reset()`.

        - info (dict): Contains auxiliary diagnostic information (helpful for
        debugging, learning, and logging). This might, for instance, contain:
        metrics that describe the agent’s performance state, variables that are
        hidden from observations, or individual reward terms that are combined
        to produce the total reward. In OpenAI Gym <v26, it contains
        `TimeLimit.truncated` to distinguish truncation and termination, however
        this is deprecated in favour of returning terminated and truncated
        variables.
        """

        if action == 1:
            self._bird.jump()

        add_pipe = False
        self._bird.move()

        to_be_removed = []
        for pipe in self._pipes:
            if pipe.x + pipe.pipe_top.get_width() < 0:
                to_be_removed.append(pipe)

            if not pipe.passed and pipe.x < self._bird.x:
                self._score += 1
                pipe.passed = True
                add_pipe = True

            pipe.move()

        if add_pipe:
            self._pipes.append(Pipe(700, self.np_random))

        for pipe in to_be_removed:
            self._pipes.remove(pipe)

        self._base.move()

        if self.render_mode == "human":
            self.render()

        return self.observation, self.reward, self.terminated, \
            self.truncated, self.info

    def reset(self, *, seed: int | None = None,
              options: Dict[str, Any] | None = None) \
            -> Tuple[ObsType, Dict[str, Any]]:
        """
        Resets the environment to an initial internal state, returning an
        initial observation and info.

        This method generates a new starting state often with some randomness to
        ensure that the agent explores the state space and learns a generalised
        policy about the environment. This randomness can be controlled with the
        seed parameter otherwise if the environment already has a random number
        generator and `reset()` is called with `seed=None`, the RNG is not
        reset.

        Therefore, `reset()` should (in the typical use case) be called with a
        seed right after initialization and then never again.

        For Custom environments, the first line of `reset()` should be
        `super().reset(seed=seed)` which implements the seeding correctly.

        Parameters:
        - seed (optional int): The seed that is used to initialize the
        environment’s PRNG (`np_random`). If the environment does not already
        have a PRNG and `seed=None` (the default option) is passed, a seed will
        be chosen from some source of entropy (e.g. timestamp or /dev/urandom).
        However, if the environment already has a PRNG and `seed=None` is
        passed, the PRNG will not be reset. If you pass an integer, the PRNG
        will be reset even if it already exists. Usually, you want to pass an
        integer right after the environment has been initialized and then never
        again.

        - options (optional dict): Additional information to specify how the
        environment is reset (optional, depending on the specific environment).

        Returns:
        - observation (ObsType): Observation of the initial state. This will be
        an element of `observation_space` (typically a numpy array) and is
        analogous to the observation returned by `step()`.

        - info (dictionary): This dictionary contains auxiliary information
        complementing observation. It should be analogous to the info returned
        by `step()`.
        """

        super().reset(seed=seed)

        self._background = Background()
        self._pipes = [Pipe(700, self.np_random)]
        self._base = Base(700)
        self._bird = Bird(222, 376)

        self._surface = None

        self._last_action = 0
        self._score = 0

        if self.render_mode is not None:
            self.render()

        return self.observation, self.info

    def render(self) -> RenderFrame | List[RenderFrame] | None:
        """
        Compute the render frames as specified by render_mode during the
        initialization of the environment.

        The environment’s metadata render modes (`env.metadata[“render_modes”]`)
        should contain the possible ways to implement the render modes. In
        addition, list versions for most render modes is achieved through
        `gymnasium.make` which automatically applies a wrapper to collect
        rendered frames.

        Note: As the render_mode is known during `__init__`, the objects used to
        render the environment state should be initialised in `__init__`.

        By convention, if the render_mode is:
        - None (default): no render is computed.

        - "human": The environment is continuously rendered in the current
        display or terminal, usually for human consumption. This rendering
        should occur during `step()` and `render()` doesn’t need to be called.
        Returns None.

        - "rgb_array": Return a single frame representing the current state of
        the environment. A frame is a `np.ndarray` with shape (x, y, 3)
        representing RGB values for an x-by-y pixel image.
        """

        if self._surface is None:
            pygame.init()

            if self.render_mode == "human":
                pygame.display.init()
                pygame.display.set_caption("Flappy Bird")
                self._surface = pygame.display.set_mode(self._shape)
            elif self.render_mode == "rgb_array":
                self._surface = pygame.Surface(self._shape)
                return self.observation

        assert self._surface is not None, \
            "Something went wrong with pygame. This should never happen."

        self._background.draw(self._surface)
        for pipe in self._pipes:
            pipe.draw(self._surface)
        self._base.draw(self._surface)
        self._bird.draw(self._surface)

        if self.render_mode == "human":
            pygame.event.pump()
            pygame.display.update()
            self._clock.tick(FlappyBirdEnv.metadata["render_fps"])
        elif self.render_mode == "rgb_array":
            return self.observation

    @property
    @functools.cache
    def _width(self) -> int:
        return FlappyBirdEnv.observation_space.shape[1]

    @property
    @functools.cache
    def _height(self) -> int:
        return FlappyBirdEnv.observation_space.shape[0]

    @property
    @functools.cache
    def _shape(self) -> Tuple[int, int]:
        return self._width, self._height

    def close(self) -> None:
        """
        After the user has finished using the environment, close contains the
        code necessary to "clean up" the environment.

        This is critical for closing rendering windows, database or HTTP
        connections.
        """

        if self._surface is not None:
            pygame.display.quit()
            pygame.quit()
