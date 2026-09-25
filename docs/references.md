# Sources used

## CUDA backend sources inspected on 2026-09-21

- Lan et al., [WarpDrive: Fast End-to-End Deep Multi-Agent Reinforcement Learning
  on a GPU](https://jmlr.org/papers/v23/22-0185.html), 2022; also inspected the
  [project README](https://github.com/salesforce/warp-drive). Used the architectural
  idea of batching simulation and retaining training tensors on-device. No code
  was copied, and published speedups are not laptop measurements.
- CuPy **v13.6.0** versioned [kernel guide](https://raw.githubusercontent.com/cupy/cupy/v13.6.0/docs/source/user_guide/kernel.rst)
  and [interoperability guide](https://raw.githubusercontent.com/cupy/cupy/v13.6.0/docs/source/user_guide/interoperability.rst).
  Inspected RawModule/RawKernel compilation, DLPack ownership and ExternalStream
  contracts. Used these APIs directly and checked Windows execution locally.
- NVIDIA Python wheels `nvidia-cuda-runtime-cu12==12.8.90` and
  `nvidia-cuda-nvrtc-cu12==12.8.93`: inspected installed headers/DLL layout and
  verified kernel compilation without a global toolkit. These are optional
  runtime dependencies; core gameplay remains dependency-free.

Reviewed on 2026-09-20 while establishing this project. These sources informed design;
their presence does not establish that any learning algorithm will solve this game.
No code or artwork from the PvZ reference projects was copied.

| Source | Evidence inspected | Decision informed |
|---|---|---|
| [Gymnasium: A Standard Interface for Reinforcement Learning Environments](https://arxiv.org/abs/2407.17032), Towers et al., 2024 | Paper abstract and [environment API documentation](https://gymnasium.farama.org/api/env/) | Explicit reset/step lifecycle, detached observations, separate rendering, and explicit outcomes. The framework adapter remains outside this repository. |
| [A Closer Look at Invalid Action Masking in Policy Gradient Algorithms](https://arxiv.org/abs/2006.14171), Huang and Ontañón, 2020 | Paper abstract and stated masking rationale | Provide a complete legal-action query backed by the same validator as execution, so an external adapter can construct masks reliably. |
| [Leveraging Procedural Generation to Benchmark Reinforcement Learning](https://arxiv.org/abs/1912.01588), Cobbe et al., 2019/2020 | Paper abstract and generalization motivation | Seeded wave generation, fixed resolved schedules, and support for future separation of training and evaluation seeds. |
| [PythonPlantsVsZombies](https://github.com/marblexu/PythonPlantsVsZombies), marblexu | README, `source/constants.py`, and `source/state/level.py`; [revision afc4ae12](https://github.com/marblexu/PythonPlantsVsZombies/commit/afc4ae12c7a19bee5aaa2c20e9d765e1afcccd80) | Concrete daytime mechanics, human controls, and configuration-driven level content. Its display-time dependencies reinforced the need for a separate fixed-tick engine here. |
| [PvZ_RL](https://github.com/ubaidill-chem/PvZ_RL), ubaidill-chem | README and `game_logic.py`; [revision 166e1f12](https://github.com/ubaidill-chem/PvZ_RL/commit/166e1f121aa3df629fad7067ed8898cfa4bdb3b7) | Separate simulation and display, seeded spawn rosters, public planting controls. Population-delta counters motivated explicit spawn and defeat events here. |
| [pygame-ce timing documentation](https://pyga.me/docs/ref/time.html) | Clock and timer API documentation | Use the display clock only to pace the UI; it never supplies game-rule timestamps. |
| [Blizzard s2client-proto](https://github.com/Blizzard/s2client-proto), revision `7212ae512d15aa93a708e025d3ab9af4a9c4138f` | `s2clientprotocol/sc2api.proto`: RequestStartReplay, RequestStep, ResponseObservation, and RequestSaveReplay/ResponseSaveReplay; inspected 2026-09-20 | Separate saved replay data, simulation stepping, observation/action feedback, and live presentation. Lawn Lab uses its own existing deterministic action format, not SC2's binary format; no SC2 code was copied. |
| [pygame-ce Surface documentation](https://pyga.me/docs/ref/surface.html) and [image byte conversion](https://pyga.me/docs/ref/image.html) | Surface creation, clipping, and `image.tobytes` contracts | Render without a display; return independent surfaces or packed RGB24 bytes without NumPy. |
| [Gymnasium environment API](https://gymnasium.farama.org/api/env/) | Rendering modes and environment outcome boundaries | Expose rendering separately from stepping; keep external truncation out of the game outcome and policy observations. |
| Local research integration in `E:/Projects/Tower-Defence-AI/PVZ-plant` at revision `8a132bcf079ec6c1b68ef49c114f660f200d1966` | `docs/engine-notes.md` dated 2026-09-20 against engine commit `b3cfbd886ab378313a1fdb57ee43a9a1b36a0793`; `src/pvz_rl/rendering.py`, `video.py`, and `provenance.py` | Optional replay metadata, caller-supplied checkpoint provenance, a shared offscreen board/HUD API, and a new source pin for consumers. These files informed integration requirements; their code was not copied. |

The GitHub APIs and repository roots did not provide a standard reusable license for the
two PvZ references at the inspected revisions. They were therefore treated as references,
with a fresh implementation and original primitive-based illustrations.

The inspected references do not supply this game's exact balance. All shipped costs,
health, timing, and speed values are this project's explicit `daytime-1.0` preset.

Other projects and papers encountered during discovery were not adopted as implementation
dependencies or as evidence of verified win rates. This project makes no RL performance claim.

## Research replay compatibility — 2026-09-21

Inspected `PVZ-plant/src/pvz_rl/recordings.py` and `action_timing.py` at research
commit `665aec5` (reader introduced earlier). The explicit `pvz-rl/actions-v1`
contract permits zero-tick planting/digging; version 1 requires positive ticks.
The native adapter follows that contract and reuses native seek/hash machinery.
Local evidence: the shared checkpoint `ce6b6fc3b480233c67b4009e6ce44d7412d2e2ef8fc7db8c047d34fe70fbb65e`
has easy/standard/hard demos ending at ticks 4226/4184/5074 with matching hashes.
This is a format compatibility fix, with no new learning or combat claim.


## PC mechanics inspection — 2026-09-25

- [Patoke PC reconstruction](https://github.com/Patoke/re-plants-vs-zombies/tree/c4692036c5e11d227c8fb7c593b734dac96da028): inspected Plant.cpp, Zombie.cpp, Board.cpp, SeedPacket.cpp, LawnMower.cpp and TodCommon.cpp; Reanimator.cpp supplies frame-rate conversion. Used for production ranges, firing phases, initial recharge, health, head loss, autonomous decay, bite age and mower slowdown. This is a community reconstruction, not an authoritative binary equivalence test.
- [Animation reference](https://github.com/Bamcane/re-plants-vs-zombies/tree/0f6bbd39302acf69484ba8b3e071724e35cfba17/pak/reanim): inspected PotatoMine.reanim, Chomper.reanim, Zombie.reanim and Zombie_polevaulter.reanim for frame counts and ground-track structure. Only timing facts informed the independent implementation; no artwork/assets are included. Movement and tile collisions retain the limits documented in the mechanics derivation.
