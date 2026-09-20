"""Run from any folder after installing the game package. No private imports or UI."""

from pvz_game import Game, Place, Status, Wait

game = Game()
observation = game.reset(level="easy", seed=42)
while observation.status == Status.RUNNING:
    action = Wait()
    # This intentionally small integration example fills a back column with shooters.
    for row in range(observation.rows):
        candidate = Place("peashooter", row, 0)
        if game.validate_action(candidate).accepted:
            action = candidate
            break
    result = game.step(action, ticks=4)
    observation = result.observation

print(observation.status.value, observation.counts)
