import datetime
from django.utils import timezone
from rest_framework.response import Response
from rest_framework import status
from .models import Task

def update_time_spent(request, task_id):
    """
    Standalone function to update time spent on a task based on session timing
    """
    try:
        task = Task.objects.get(pk=task_id)
        
        if request.user != task.user:
            return Response(
                {"message": "You are not allowed to update time spent for this task"},
                status=status.HTTP_403_FORBIDDEN,
            )
        
        # Get session timestamps
        session_start = request.data.get("session_start")
        session_end = request.data.get("session_end", timezone.now().isoformat())
        
        if not session_start:
            return Response(
                {"message": "Missing session_start parameter"},
                status=status.HTTP_400_BAD_REQUEST,
            )
        
        try:
            # Parse timestamps
            start_time = datetime.datetime.fromisoformat(session_start.replace('Z', '+00:00'))
            end_time = datetime.datetime.fromisoformat(session_end.replace('Z', '+00:00'))
            
            # Calculate elapsed seconds (with bounds checking)
            elapsed_seconds = max(0, min((end_time - start_time).total_seconds(), 8 * 60 * 60))  # Cap at 8 hours
            elapsed_seconds = int(elapsed_seconds)  # Convert to integer
            
            # Update task's time_spent field
            if task.time_spent is None:
                task.time_spent = elapsed_seconds
            else:
                task.time_spent += elapsed_seconds
            
            task.save(update_fields=['time_spent'])
            
            return Response({
                "message": "Time spent updated successfully",
                "time_spent": task.time_spent,
                "elapsed_seconds": elapsed_seconds
            }, status=status.HTTP_200_OK)
            
        except ValueError:
            return Response(
                {"message": "Invalid timestamp format. Use ISO format (YYYY-MM-DDTHH:MM:SS.sssZ)"},
                status=status.HTTP_400_BAD_REQUEST,
            )
            
    except Task.DoesNotExist:
        return Response(
            {"message": "Task not found"},
            status=status.HTTP_404_NOT_FOUND,
        )