def extract_google_drive_link_id(url):
    """
    Extracts the Google Drive file ID from a given URL
    """
    # If the word id is present in the link 
    if 'id' in url: 
        # Split the URL by the word id
        file_id = url.split('id=')[1] 
        
        # If the word export is present in the link
        if 'export' in file_id: 
            # Split the URL by the word export
            file_id = file_id.split('&export')[0] 

        # Return the ID
        return {"data": file_id, "valid": True}
    
    elif 'file/d/' in url:
        file_id = url.split('file/d/')[1]
        if '/' in file_id:
            file_id = file_id.split('/')[0]
        return {"data": file_id, "valid": True}

    else: 
        return {"data": "Invalid Google Drive URL", "valid": False}
