"""An explicit public Instagram review, never a claim of automated access."""
from .core import Observation, now, public_url, timestamp
from .storage import commit_case

ACCESS_STATUSES = ('Not checked', 'Public view reviewed', 'Restricted / login required', 'Unavailable')
OBSERVATION_BASES = ('Public page observation', 'Supplied evidence transcription', 'Unverified note')
PROFILE_FIELDS = ('Display name', 'Biography', 'Post count', 'Follower count', 'Following count',
                  'Public link', 'Visibility', 'Public activity note')


def profile_url(case):
    return f'https://www.instagram.com/{case.username}/'


def checklist(case):
    excluded = {e.id for e in case.evidence if e.excluded}
    result = []
    for field in PROFILE_FIELDS:
        observations = [o for o in case.observations if o.field == field and o.basis != 'Unverified note']
        state = 'not recorded'
        if observations:
            state = 'recorded' if any(o.evidence_id not in excluded for o in observations) else 'support excluded'
        result.append((field, state))
    return result


def review_access(case, directory, status, checked_at='', notes=''):
    if status not in ACCESS_STATUSES:
        raise ValueError('Unknown Instagram access status.')
    time = timestamp(checked_at) if checked_at else None
    if status != 'Not checked' and time is None:
        raise ValueError('An access review requires an explicit time with a timezone.')
    def edit(draft):
        draft.instagram_review.access_status = status
        draft.instagram_review.checked_at = time
        draft.instagram_review.notes = notes
        draft.audit_log.append({'at': now(), 'action': 'instagram_access_review', 'status': status,
                                'observed_at': time, 'source_url': profile_url(draft), 'basis': 'Investigator supplied'})
    commit_case(case, directory, edit)


def record_observation(case, directory, field, value, source_url, observed_at, evidence_id='', basis=OBSERVATION_BASES[0]):
    if field not in PROFILE_FIELDS or basis not in OBSERVATION_BASES:
        raise ValueError('Choose a supported profile field and observation basis.')
    if not value.strip():
        raise ValueError('Enter an observation value.')
    source_url = public_url(source_url)
    time = timestamp(observed_at)
    if time is None:
        raise ValueError('Observation time requires an explicit timezone.')
    if evidence_id and evidence_id not in {e.id for e in case.evidence if not e.excluded}:
        raise ValueError('Supporting evidence must be an active imported file.')
    if basis == 'Supplied evidence transcription' and not evidence_id:
        raise ValueError('Attach the supporting evidence ID for an evidence transcription.')
    item = Observation(field, value.strip(), source_url, time, evidence_id, basis=basis)
    def edit(draft):
        draft.observations.append(item)
        draft.audit_log.append({'at': now(), 'action': 'profile_observation_recorded', 'field': field, 'basis': basis})
    commit_case(case, directory, edit)
    return item
