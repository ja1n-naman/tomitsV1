import pytest

from tomits import services as svc
from tomits.models import TaskStatus


@pytest.mark.parametrize("close", [svc.fail_task, svc.skip_task])
@pytest.mark.parametrize("reason", ["", "   ", "\n\t", None])
def test_blank_reason_is_rejected_and_task_stays_open(session, close, reason):
    task = svc.add_task(session, "Write report", 60)
    with pytest.raises(svc.TaskError):
        close(session, task.id, reason)
    session.refresh(task)
    assert task.status == TaskStatus.PENDING.value
    assert task.reasons == []
    assert task.closed_at is None


@pytest.mark.parametrize("close,status", [(svc.fail_task, "failed"), (svc.skip_task, "skipped")])
def test_reason_is_saved_with_status(session, close, status):
    task = svc.add_task(session, "Gym", 45)
    close(session, task.id, "  meeting ran late  ")
    session.refresh(task)
    assert task.status == status
    assert task.latest_reason == "meeting ran late"
    assert task.reasons[0].status == status
    assert task.closed_at is not None


def test_done_needs_no_reason(session):
    task = svc.add_task(session, "Read", 20)
    svc.complete_task(session, task.id)
    assert task.status == TaskStatus.DONE.value
    assert task.reasons == []


def test_closed_task_cannot_be_closed_again(session):
    task = svc.add_task(session, "Read", 20)
    svc.fail_task(session, task.id, "tired")
    with pytest.raises(svc.TaskError):
        svc.complete_task(session, task.id)
    with pytest.raises(svc.TaskError):
        svc.skip_task(session, task.id, "another reason")
