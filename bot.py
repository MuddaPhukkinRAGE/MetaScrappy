    except Exception as error:
        print(f"PRICE LOOKUP ERROR: {type(error).__name__}: {error}")
        await interaction.followup.send(
            f"Price lookup failed: `{type(error).__name__}`. "
            "Check Render logs for details."
        )
