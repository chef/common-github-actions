#TODO: items

1. identify affected repos (needing common GH action)
	- list of repos finalized for limited GA
2. prototype each GH action	on https://github.com/chef/chef-vault
	- sonar - public repos - the Jason way (new runner)
		- API tokens created - done...
		- correct project_name in properties? 
	- blackduck	
		- request all repos to Jason
	- polaris
	- truffle hog - done...?
	- scc and any othertools from previous GA's
	- dependabot scanning (manual) 
	- ad hoc CD - intel cve-bin tool
    - add OSSF scorecard? https://github.com/actions/starter-workflows/blob/main/code-scanning/scorecard.yml
	
3. first 10 repos
4. have teams do next round

## copy PR-v2.yml & stub to other 3 common-github-actions repos
1. https://github.com/habitat-sh/common-github-actions
1. https://github.com/inspec/common-github-actions

## set up secrets like
- https://github.com/chef/chef/settings/secrets/actions

## set up sonar.properties from references
- https://github.com/progress-platform-services/chef-node-management-cli/blob/main/sonar-project.properties
- https://github.com/progress-platform-services/chef-node-management-cli
- go-based one (Sonar Cloud) - https://github.com/chef/automate/blob/main/sonar-project.properties (goes to https://sonar.progress.com/dashboard?id=Chef_Automate&codeScope=overall, convert project name to Chef_Automate instead of automate_automate)
- https://github.com/progress-platform-services/chef-node-management-cli/blob/main/.github/workflows/sonarqube.yml
- https://github.com/chef/chef-server/blob/0ae871a00deb405ed068f2b8b1854b0660413a77/sonar-project.properties#L7

needs work
- https://github.com/chef/ohai/blob/main/sonar-project.properties
- https://github.com/chef/chef/blob/main/sonar-project.properties

ref- https://docs.sonarsource.com/sonarqube-server/latest/analyzing-source-code/languages/ruby/

## Blackduck
SCA needs BLACKDUCK_URL and secrets.BLACKDUCK_TOKEN
can upload SARIF to GitHub Adv Security in advanced example

Polaris needs POLARIS_SERVER_URL, secrets.POLARIS_ACCESS_TOKEN

Coverity needs COVERITY_URL, COVERITY_USER, secrets.COVERITY_PASSPHRASE

## copy to test repos
### chef
- https://github.com/chef/mixlib-cli

- https://github.com/inspec/train-habitat
- https://github.com/inspec/k8s-ruby

## upgrade all common stubs to progress-platform-sevices
- look at all the junk in https://github.com/progress-platform-services/chef-state-api workflows

## generate Sonar reports for limited GA
https://www.bitegarden.com/how-to-create-sonarqube-report

## add container stuff
https://github.com/actions/starter-workflows/blob/main/code-scanning/kubesec.yml
https://github.com/actions/starter-workflows/blob/main/code-scanning/snyk-container.yml

Evaluate other tools:
https://github.com/actions/starter-workflows/blob/main/code-scanning/sysdig-scan.yml
https://github.com/actions/starter-workflows/blob/main/code-scanning/trivy.yml