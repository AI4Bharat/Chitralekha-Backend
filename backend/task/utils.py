def update_task_completion_status(task, user, status, audio_url=None):
    """
    Update task completion information when status changes.
    
    Parameters:
    task (Task): The task object being updated
    user (User): User completing the task
    status (str): New status of the task
    audio_url (str, optional): URL of generated audio for voiceover tasks
    """
    import datetime
    
    # Initialize completed field if it doesn't exist
    if not task.completed:
        task.completed = {}
    
    # Update with completion info
    task.completed.update({
        'completed_by': user.id,
        'completed_by_name': f"{user.first_name} {user.last_name}",
        'completed_by_email': user.email,
        'completed_at': datetime.datetime.now().isoformat(),
        'final_status': status
    })
    
    # For voiceover tasks, add the audio URL when moving from POST_PROCESS to COMPLETE
    if audio_url and status == "COMPLETE" and task.status == "POST_PROCESS":
        task.completed['audio_url'] = audio_url
    
    task.status = status
    task.save()