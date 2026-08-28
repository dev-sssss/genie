import json

import os

FILE_PATH = os.path.join(os.path.dirname(__file__), "templates.json")

with open(FILE_PATH, "r", encoding="utf-8") as f:
    data = json.load(f)

# 1. E2E testing (Playwright)
e2e_playwright = {
    "component_type": "testing",
    "identifier": "playwright_e2e_runner",
    "execution_strategy": "shell_agnostic",
    "templates": {
        "github_actions": "      - name: Install Playwright Browsers\n        run: npx playwright install --with-deps\n      - name: Run Playwright tests\n        run: npx playwright test\n      - uses: actions/upload-artifact@v4\n        if: always()\n        with:\n          name: playwright-report\n          path: playwright-report/\n          retention-days: 30",
        "gitlab_ci": "  image: mcr.microsoft.com/playwright:v1.41.0-jammy\n  script:\n    - npm ci\n    - npx playwright test\n  artifacts:\n    when: always\n    paths:\n      - playwright-report/\n    expire_in: 30 days",
        "jenkins": "                    sh '''\n                        npm ci\n                        npx playwright install --with-deps\n                        npx playwright test\n                    '''\n                    archiveArtifacts artifacts: 'playwright-report/**', fingerprint: true, allowEmptyArchive: true",
        "azure_devops": "          - script: |\n              npm ci\n              npx playwright install --with-deps\n              npx playwright test\n            displayName: 'Run Playwright E2E Tests'\n          - task: PublishPipelineArtifact@1\n            condition: always()\n            inputs:\n              targetPath: 'playwright-report'\n              artifact: 'playwright-report'",
        "circleci": "            npm ci\n            npx playwright install --with-deps\n            npx playwright test",
        "bitbucket": "            - npm ci\n            - npx playwright install --with-deps\n            - npx playwright test\n            artifacts:\n              - playwright-report/**"
    },
    "required_variables": []
}

# 2. Security scan (CodeQL)
codeql_scan = {
    "component_type": "security_scan",
    "identifier": "codeql_sast_scan",
    "execution_strategy": "shell_agnostic",
    "templates": {
        "github_actions": "      - name: Initialize CodeQL\n        uses: github/codeql-action/init@v3\n        with:\n          languages: javascript, python\n      - name: Perform CodeQL Analysis\n        uses: github/codeql-action/analyze@v3",
        "gitlab_ci": "  script:\n    - echo 'Use GitLab Ultimate SAST instead or run CodeQL CLI manually'",
        "jenkins": "                    sh 'echo \"CodeQL requires GitHub Advanced Security or manual CLI integration\"'",
        "azure_devops": "          - script: echo 'CodeQL requires manual CLI configuration on Azure'",
        "circleci": "            echo 'CodeQL not natively integrated via simple wrapper on CircleCI'",
        "bitbucket": "            - echo 'CodeQL requires manual CLI on Bitbucket'"
    },
    "required_variables": []
}

# 3. Security (Snyk Container / Dependency)
snyk_scan = {
    "component_type": "security_scan",
    "identifier": "snyk_vulnerability_scan",
    "execution_strategy": "shell_agnostic",
    "templates": {
        "github_actions": "      - name: Run Snyk to check for vulnerabilities\n        uses: snyk/actions/node@master\n        env:\n          SNYK_TOKEN: ${{ secrets.SNYK_TOKEN }}\n        with:\n          command: monitor",
        "gitlab_ci": "  image: node:latest\n  script:\n    - npm install -g snyk\n    - snyk auth $SNYK_TOKEN\n    - snyk test || true\n    - snyk monitor",
        "jenkins": "                    sh '''\n                        npm install -g snyk\n                        snyk auth $SNYK_TOKEN\n                        snyk test || true\n                        snyk monitor\n                    '''",
        "azure_devops": "          - script: |\n              npm install -g snyk\n              snyk auth $(SNYK_TOKEN)\n              snyk test || true\n              snyk monitor\n            displayName: 'Snyk Security Scan'",
        "circleci": "            npm install -g snyk\n            snyk auth $SNYK_TOKEN\n            snyk test || true\n            snyk monitor",
        "bitbucket": "            - npm install -g snyk\n            - snyk auth $SNYK_TOKEN\n            - snyk test || true\n            - snyk monitor"
    },
    "required_variables": ["SNYK_TOKEN"]
}

# 4. Teams Alerting 
teams_alert = {
    "component_type": "alerting",
    "identifier": "teams_webhook",
    "execution_strategy": "shell_agnostic",
    "templates": {
        "github_actions": "      - name: Send Microsoft Teams Notification\n        run: |\n          STATUS=\"${{ needs.deploy.result == 'success' && 'SUCCESS' || 'FAILED' }}\"\n          curl -H \"Content-Type: application/json\" -d \"{\\\"title\\\": \\\"Pipeline $STATUS\\\", \\\"text\\\": \\\"Repo: ${{ github.repository }} | Branch: ${{ github.ref_name }}\\\"}\" ${{ secrets.TEAMS_WEBHOOK_URL }}",
        "gitlab_ci": "    - |\n      STATUS=\"SUCCESS\"\n      if [ \"${CI_JOB_STATUS}\" != \"success\" ]; then STATUS=\"FAILED\"; fi\n      curl -H \"Content-Type: application/json\" -d \"{\\\"title\\\": \\\"Pipeline $STATUS\\\", \\\"text\\\": \\\"Project: $CI_PROJECT_NAME | Branch: $CI_COMMIT_REF_NAME\\\"}\" $TEAMS_WEBHOOK_URL",
        "jenkins": "                    sh '''\n                        STATUS=\"SUCCESS\"\n                        if [ \"$currentBuild.currentResult\" != \"SUCCESS\" ]; then STATUS=\"FAILED\"; fi\n                        curl -H \"Content-Type: application/json\" -d \"{\\\"title\\\": \\\"Pipeline $STATUS\\\", \\\"text\\\": \\\"Job: $JOB_NAME | Build: $BUILD_NUMBER\\\"}\" $TEAMS_WEBHOOK_URL\n                    '''",
        "azure_devops": "          - script: |\n              curl -H \"Content-Type: application/json\" -d \"{\\\"title\\\": \\\"Pipeline Finished\\\", \\\"text\\\": \\\"Repo: $(Build.Repository.Name) | Branch: $(Build.SourceBranchName)\\\"}\" $(TEAMS_WEBHOOK_URL)\n            displayName: 'Microsoft Teams Notification'",
        "circleci": "            curl -H \"Content-Type: application/json\" -d \"{\\\"title\\\": \\\"Pipeline Finished\\\", \\\"text\\\": \\\"Project: $CIRCLE_PROJECT_REPONAME | Branch: $CIRCLE_BRANCH\\\"}\" $TEAMS_WEBHOOK_URL",
        "bitbucket": "            - curl -H \"Content-Type: application/json\" -d \"{\\\"title\\\": \\\"Pipeline Finished\\\", \\\"text\\\": \\\"Repo: $BITBUCKET_REPO_SLUG | Branch: $BITBUCKET_BRANCH\\\"}\" $TEAMS_WEBHOOK_URL"
    },
    "required_variables": ["TEAMS_WEBHOOK_URL"]
}

# 5. Serverless - AWS Lambda
lambda_deploy = {
    "component_type": "deployment_target",
    "identifier": "aws_lambda_deploy",
    "execution_strategy": "shell_agnostic",
    "templates": {
        "github_actions": "      - name: Deploy to AWS Lambda\n        run: |\n          zip -r function.zip .\n          aws lambda update-function-code --function-name ${{ vars.LAMBDA_FUNCTION_NAME }} --zip-file fileb://function.zip",
        "gitlab_ci": "    - zip -r function.zip .\n    - aws lambda update-function-code --function-name $LAMBDA_FUNCTION_NAME --zip-file fileb://function.zip",
        "jenkins": "                    sh '''\n                        zip -r function.zip .\n                        aws lambda update-function-code --function-name $LAMBDA_FUNCTION_NAME --zip-file fileb://function.zip\n                    '''",
        "azure_devops": "          - script: |\n              zip -r function.zip .\n              aws lambda update-function-code --function-name $(LAMBDA_FUNCTION_NAME) --zip-file fileb://function.zip\n            displayName: 'Deploy to AWS Lambda'",
        "circleci": "            zip -r function.zip .\n            aws lambda update-function-code --function-name $LAMBDA_FUNCTION_NAME --zip-file fileb://function.zip",
        "bitbucket": "            - zip -r function.zip .\n            - aws lambda update-function-code --function-name $LAMBDA_FUNCTION_NAME --zip-file fileb://function.zip"
    },
    "required_variables": ["LAMBDA_FUNCTION_NAME"]
}

# 6. S3 + CloudFront Static Hosting
s3_deploy = {
    "component_type": "deployment_target",
    "identifier": "s3_cloudfront_deploy",
    "execution_strategy": "shell_agnostic",
    "templates": {
        "github_actions": "      - name: Deploy to S3 and invalidate CloudFront\n        run: |\n          aws s3 sync dist/ s3://${{ vars.S3_BUCKET_NAME }} --delete\n          aws cloudfront create-invalidation --distribution-id ${{ vars.CLOUDFRONT_DISTRIBUTION_ID }} --paths '/*'",
        "gitlab_ci": "    - aws s3 sync dist/ s3://$S3_BUCKET_NAME --delete\n    - aws cloudfront create-invalidation --distribution-id $CLOUDFRONT_DISTRIBUTION_ID --paths '/*'",
        "jenkins": "                    sh '''\n                        aws s3 sync dist/ s3://$S3_BUCKET_NAME --delete\n                        aws cloudfront create-invalidation --distribution-id $CLOUDFRONT_DISTRIBUTION_ID --paths '/*'\n                    '''",
        "azure_devops": "          - script: |\n              aws s3 sync dist/ s3://$(S3_BUCKET_NAME) --delete\n              aws cloudfront create-invalidation --distribution-id $(CLOUDFRONT_DISTRIBUTION_ID) --paths '/*'\n            displayName: 'Deploy to S3 & Invalidate CloudFront'",
        "circleci": "            aws s3 sync dist/ s3://$S3_BUCKET_NAME --delete\n            aws cloudfront create-invalidation --distribution-id $CLOUDFRONT_DISTRIBUTION_ID --paths '/*'",
        "bitbucket": "            - aws s3 sync dist/ s3://$S3_BUCKET_NAME --delete\n            - aws cloudfront create-invalidation --distribution-id $CLOUDFRONT_DISTRIBUTION_ID --paths '/*'"
    },
    "required_variables": ["S3_BUCKET_NAME", "CLOUDFRONT_DISTRIBUTION_ID"]
}

# 7. Approval Gate
approval_gate = {
    "component_type": "approval_gate",
    "identifier": "manual_approval_gate",
    "execution_strategy": "platform_specific",
    "templates": {
        "github_actions": "    environment:\n      name: production\n      url: https://my-app.com",
        "gitlab_ci": "  when: manual\n  environment:\n    name: production",
        "jenkins": "        stage('Approval') {\n            steps {\n                timeout(time: 2, unit: 'DAYS') {\n                    input message: 'Approve deployment to production?'\n                }\n            }\n        }",
        "azure_devops": "  - stage: Approval\n    jobs:\n    - job: waitForValidation\n      displayName: Wait for manual validation\n      pool: server\n      timeoutInMinutes: 4320 # job times out in 3 days\n      steps:\n      - task: ManualValidation@0\n        timeoutInMinutes: 1440\n        inputs:\n          notifyUsers: | \n            someone@example.com\n          instructions: 'Please validate the build configuration and resume'",
        "circleci": "      - approve_deploy:\n          type: approval\n          requires:\n            - test",
        "bitbucket": "          trigger: manual"
    },
    "required_variables": []
}

# 8. SSH Key Cleanup
ssh_cleanup = {
    "component_type": "cleanup",
    "identifier": "ssh_key_cleanup",
    "execution_strategy": "shell_agnostic",
    "templates": {
        "github_actions": "      - name: Cleanup SSH Key\n        if: always()\n        run: rm -f ~/.ssh/deploy_key",
        "gitlab_ci": "  after_script:\n    - rm -f ~/.ssh/deploy_key",
        "jenkins": "        always {\n            sh 'rm -f ~/.ssh/deploy_key || true'\n        }",
        "azure_devops": "          - script: rm -f ~/.ssh/deploy_key\n            displayName: 'Cleanup SSH Key'\n            condition: always()",
        "circleci": "            rm -f ~/.ssh/deploy_key",
        "bitbucket": "          after-script:\n            - rm -f ~/.ssh/deploy_key"
    },
    "required_variables": []
}

new_items = [e2e_playwright, codeql_scan, snyk_scan, teams_alert, lambda_deploy, s3_deploy, approval_gate, ssh_cleanup]

data.extend(new_items)

with open(FILE_PATH, "w", encoding="utf-8") as f:
    json.dump(data, f, indent=2)

print("Updated data/templates.json with missing components.")
