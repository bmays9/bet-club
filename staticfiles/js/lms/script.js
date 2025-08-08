document.addEventListener('DOMContentLoaded', function () {
    const links = document.querySelectorAll('.select-team');
    const input = document.querySelector('#id_team_name');
    const button = document.querySelector('button[type="submit"]');
    const label = document.getElementById('selected-team-label');

    button.disabled = true;

    links.forEach(link => {
        link.addEventListener('click', function (e) {
            e.preventDefault();
            const team = this.getAttribute('data-team');
            input.value = team;
            button.disabled = false;

            if (label) {
                label.textContent = team;
            }

            document.querySelectorAll('.team-selected').forEach(el => {
                el.classList.remove('team-selected');
            });

            this.classList.add('team-selected');
        });
    });

    const form = document.querySelector('form');
    form.addEventListener('submit', function (e) {
        if (!input.value) {
            e.preventDefault();
            showToast("Please select a team before submitting.", true);
        } else {
            showToast(`You picked ${input.value}!`, false);
        }
    });

    function showToast(message, isError) {
        const toastEl = document.getElementById('pickToast');
        const toastBody = toastEl.querySelector('.toast-body');

        toastBody.textContent = message;

        // Change color based on error or success
        toastEl.classList.remove('bg-success', 'bg-danger');
        toastEl.classList.add(isError ? 'bg-danger' : 'bg-success');

        const toast = new bootstrap.Toast(toastEl);
        toast.show()
        delay: 4000;
    }
});