
NEW_VERSION=$1
REPO_PATH=/tmp/community-operators-prod
operator-sdk bundle validate ${REPO_PATH}/operators/openstack-lightspeed-operator/${NEW_VERSION}
operator-sdk scorecard ${REP_PATH}/operators/openstack-lightspeed-operator/${NEW_VERSION}
