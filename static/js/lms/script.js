document.addEventListener('DOMContentLoaded', function() {
    const links = document.querySelectorAll('.select-team');
    const input = document.querySelector('#id_team_name');
    const button = document.querySelector('button[type="submit"]');

    // keep button disabled initially
    button.disabled = true;

    links.forEach(link => {
        link.addEventListener('click', function(e) {
            e.preventDefault();
            const team = this.getAttribute('data-team');
            input.value = team;

            // update UI label
            const label = document.getElementById('selected-team-label');
            if (label) {
                label.textContent = team;
            }

            // enable submit button once a team is selected
            button.disabled = false;
        });
    });
});
