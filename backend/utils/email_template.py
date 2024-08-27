def send_email_template_with_attachment(subject, username, message):
    style_string = """
            *{ margin: 0; 
            padding: 0;
            }
            body {
            font-family: "Arial", sans-serif;
            background-color: #f2f8f8;
            margin: 0;
            padding: 0;
            padding-top: 2rem;
            }
            .container {
            background-color: #fff;
            # border: solid 1px #e1e1e1;
            border-radius: 2px;
            padding: 1.4rem;
            max-width: 380px;
            margin: auto;
            }
            .header {
            width: fit-content;
            margin: auto;
            }
            h1 {
            font-size: 1.2rem;
            font-weight: 300;
            margin: 1rem 0;
            font-family: "Segoe UI", Tahoma, Geneva, Verdana, sans-serif;
            }
            p {
            font-size: 0.8rem;
            color: #222;
            margin: 0.8rem 0;
            }
            .primary {
            color: #18621f;
            }
            .footer {
            margin-top: 1rem;
            font-size: 0.9rem;
            }
            .footer > * {
            font-size: inherit;
            }
    """

    html_code = f""" 
    <!DOCTYPE html>
                <html lang="en">
                <head>
                <meta charset="UTF-8" />
                <meta name="viewport" content="width=device-width, initial-scale=1.0" />
                <title>{subject}</title>
                <style>
                {style_string}
                </style>
                </head>
                <body style="background-color:#E4F9FE;padding:1rem">
                <div class="container">
                <header class="header">
                <h3>{subject}</h3>
                </header>
                <main>
                <div style="margin: 1rem auto; width: fit-content">
                </div>
                <div>
                <p style="font-size:14px">
                    Dear {username},
                </p>
                <p >                
                  {message}
                </p>
                <p style="font-style: italic;padding-top:1rem">
                    Thanks for contributing on Chitralekha! Kindly check the attachment below
                </p>
                <p style="font-size: 10px; color:grey">
                This email was intended for <span style="color:blue">{username}</span> If you received it by mistake, please delete it and notify the sender immediately. 
                </p>
                </div>
                </main>
                <footer class="footer">
                <p style="font-size: 0.8rem;">
                Best Regards,<br />
                Chitralekha Admin
                </p>
                </footer>
                </div>
                </body>
                </html>
    """
    return html_code


def send_email_template(subject, message):
    style_string = """
            *{ margin: 0; 
            padding: 0;
            }
            body {
            font-family: "Arial", sans-serif;
            background-color: #f2f8f8;
            margin: 0;
            padding: 0;
            padding-top: 2rem;
            }
            .container {
            background-color: #fff;
            border: solid 1px #e1e1e1;
            border-radius: 2px;
            padding: 1.4rem;
            max-width: 380px;
            margin: auto;
            }
            .header {
            width: fit-content;
            margin: auto;
            }
            h1 {
            font-size: 1.2rem;
            font-weight: 300;
            margin: 1rem 0;
            font-family: "Segoe UI", Tahoma, Geneva, Verdana, sans-serif;
            }
            p {
            font-size: 0.8rem;
            color: #222;
            margin: 0.8rem 0;
            }
            .primary {
            color: #18621f;
            }
            .footer {
            margin-top: 1rem;
            font-size: 0.9rem;
            }
            .footer > * {
            font-size: inherit;
            }
    """

    html_code = f""" 
    <!DOCTYPE html>
                <html lang="en">
                <head>
                <meta charset="UTF-8" />
                <meta name="viewport" content="width=device-width, initial-scale=1.0" />
                <title>{subject}</title>
                <style>
                {style_string}
                </style>
                </head>
                <body>
                <div class="container">
                <header class="header">
                <h3>{subject}</h3>
                </header>
                <main>
                <div style="margin: 1rem auto; width: fit-content">
                </div>
                <div>
                    <p>
                        Dear User,
                    </p>
                              
                {message}

                <p style="font-size: 10px; color:grey">
                This is an automated email. Please do not reply to this email.
                </p>
                </div>
                </main>
                <footer class="footer">
                <p style="font-size: 0.8rem;">
                Best Regards,<br />
                Chitralekha Admin
                </p>
                </footer>
                </div>
                </body>
                </html>
    """
    return html_code


def invite_email_template(subject, message, invite_link):
    style_string = """
        *{ margin: 0; 
        padding: 0;
        }
        body {
        font-family: "Arial", sans-serif;
        background-color: #f2f8f8;
        margin: 0;
        padding: 0;
        padding-top: 2rem;
        }
        .container {
        background-color: #fff;
        border: solid 1px #e1e1e1;
        border-radius: 2px;
        padding: 1.4rem;
        max-width: 380px;
        margin: auto;
        }
        .header {
        width: fit-content;
        margin: auto;
        }
        h1 {
        font-size: 1.2rem;
        font-weight: 300;
        margin: 1rem 0;
        font-family: "Segoe UI", Tahoma, Geneva, Verdana, sans-serif;
        }
        p {
        font-size: 0.9rem;
        color: #222;
        margin: 0.8rem 0;
        }
        .primary {
        color: #18621f;
        }
        .footer {
        margin-top: 1rem;
        font-size: 0.9rem;
        }
        .footer > * {
        font-size: inherit;
        }
    """

    html_code = f"""
            <!DOCTYPE html>
            <html lang="en">
            <head>
            <meta charset="UTF-8" />
            <meta name="viewport" content="width=device-width, initial-scale=1.0" />
            <title>{subject}</title>
            <style>
            {style_string}
            </style>
            </head>
            <body>
            <div class="container">
            <header class="header">
            <h3>{subject}</h3>
            </header>
            <main>
            <div style="margin: 1rem auto; width: fit-content">
            <table
            width="180"
            border="0"
            align="center"
            cellpadding="0"
            cellspacing="0"
            >
            <tbody>
            <tr>

            <td
            style="
            font-size: 12px;
            font-family: 'Zurich BT', Tahoma, Helvetica, Arial;
            text-align: center;
            color: white;
            border-radius: 1rem;
            border-width: 1px;
            background-color: rgb(44, 39, 153);

            ">
            <a target="_blank" style="text-decoration: none; color:white; font-size: 14px; display: block; padding: 0.2rem 0.5rem; " href="{invite_link}">
            Join Chitralekha Now
            </a>
            </td>
            </tr>
            </tbody>
            </table>
            </div>
            <div>
            <p>
            {message}
            </p>
            <p style="font-style: italic">
            For security purposes, please do not share the this link with
            anyone.
            </p>
            <p style="font-size: 10px; color:grey">
                If clicking the link doesn't work, you can copy and paste the link into your browser's address window, or retype it there.
                <a href="{invite_link}">{invite_link}</a>
            </p>
            </div>
            </main>
            <footer class="footer">
            <p>
            Best Regards,<br />
            Chitralekha Team
            </p>
            </footer>
            </div>
            </body>
            </html>
        """
    return html_code
