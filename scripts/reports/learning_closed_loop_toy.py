"""Print one observed-state closed loop for a scalar integrator."""


def main() -> None:
    state = 0.0
    for update in range(2):
        observation = state
        action = 1.0 - observation
        predicted_end = observation + action
        state = state + action
        print(f"update={update} observation={observation:g} action={action:g} "
              f"prediction_end={predicted_end:g} plant_state={state:g}")


if __name__ == "__main__":
    main()
