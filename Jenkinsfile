elifeLibrary {
    stage 'Checkout', {
        checkout scm
    }

    stage 'Project tests', {
        elifeLocalTests "./project_tests.sh"
    }

    elifeMainlineOnly {
        // develop -> master
        stage 'Master', {
            elifeGitMoveToBranch elifeGitRevision(), 'master'
        }

        stage 'Downstream', {
            build job: '../release/release-threadbare', wait: false
        }
    }
}
