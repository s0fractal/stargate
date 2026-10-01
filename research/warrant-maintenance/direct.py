"""Candidate transition logic on exactly the model's Boolean domain, not a loader."""


class DirectMachine:
    def step(self, state, event):
        ambiguous, one, two, pending = (
            state[key] for key in ('ambiguous', 'calls.one', 'calls.two', 'pending'))
        if event['host'] and event['reply']:  # END
            ambiguous, one, two, pending = False, False, False, False
        elif event['host']:  # CALL
            ambiguous, one, two, pending = (
                ambiguous or pending, True, one, not pending and not ambiguous)
        elif event['reply']:  # RESPONSE
            one, two, pending = two, False, False
        # REQUEST leaves the bookkeeping unchanged.
        return dict(zip(('ambiguous', 'calls.one', 'calls.two', 'pending'),
                        (ambiguous, one, two, pending)))
